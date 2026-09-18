-- The processor's own daily totals, by UTC day and currency. The independent scale.
{{ config(materialized='table') }}

with parsed as (
    select
        try_cast(_raw::json->>'$.settlement_date' as date)  as settlement_date,
        _raw::json->>'$.currency'                            as currency,
        try_cast(_raw::json->>'$.gross_minor' as bigint)     as gross_minor,
        try_cast(_raw::json->>'$.refunds_minor' as bigint)   as refunds_minor,
        try_cast(_raw::json->>'$.net_minor' as bigint)       as net_minor,
        try_cast(_raw::json->>'$.charge_count' as integer)   as charge_count,
        try_cast(_raw::json->>'$.refund_count' as integer)   as refund_count,
        _landing_file, _arrived_at, _batch_seq
    from {{ ref('bronze_settlements') }}
)

select * from parsed
where settlement_date is not null
qualify row_number() over (partition by settlement_date, currency
                           order by _arrived_at desc, _batch_seq desc) = 1
