-- Parse every bronze payment event with the parser for its API version, and say why a
-- row can't be used rather than dropping it. A view: cheap, and always the current parser.
{{ config(materialized='view') }}

with raw as (
    select *,
           case when json_valid(_raw) then _raw::json end as j
    from {{ ref('bronze_payments') }}
),

enveloped as (
    select *,
           j->>'$.id'           as event_id,
           j->>'$.type'         as event_type_raw,
           j->>'$.api_version'  as api_version,
           to_timestamp(try_cast(j->>'$.created' as bigint)) as created_at
    from raw
),

parsed as (
    select *,
           {{ parse('charge_id') }}                      as charge_id,
           {{ parse('refund_id') }}                      as refund_id,
           {{ parse('order_id') }}                       as order_id,
           try_cast({{ parse('amount') }} as bigint)     as amount_minor,
           lower({{ parse('currency') }})                as currency
    from enveloped
)

select
    event_id,
    case event_type_raw when 'charge.succeeded' then 'capture'
                        when 'charge.refunded'  then 'refund' end as event_type,
    api_version, charge_id, refund_id, order_id, amount_minor, currency, created_at,
    case
        when j is null                                        then 'unparseable_json'
        when api_version not in ('{{ enabled_parsers() | join("', '") }}')
                                                              then 'unsupported_api_version'
        when event_type_raw not in ('charge.succeeded', 'charge.refunded')
                                                              then 'unknown_event_type'
        when event_id is null or created_at is null           then 'missing_envelope'
        when order_id is null                                 then 'missing_order_id'
        when amount_minor is null or amount_minor <= 0        then 'bad_amount'
        when currency not in ('cad', 'usd')                   then 'unknown_currency'
        when event_type_raw = 'charge.refunded' and refund_id is null
                                                              then 'missing_refund_id'
    end as quarantine_reason,
    _raw, _bronze_row, _batch_seq, _arrived_at, _ingested_at
from parsed
