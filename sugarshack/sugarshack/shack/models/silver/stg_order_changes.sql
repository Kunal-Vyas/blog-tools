-- Parse Debezium-style change events. A delete carries the row in `before`, everything
-- else in `after`; either way we want the row image and the log sequence number.
{{ config(materialized='view') }}

with raw as (
    select *,
           case when json_valid(_raw) then _raw::json end as j
    from {{ ref('bronze_orders') }}
),

parsed as (
    select *,
           j->>'$.op'                                     as op,
           try_cast(j->>'$.source.lsn' as bigint)         as lsn,
           case when j->>'$.op' = 'd' then j->'$.before' else j->'$.after' end as r
    from raw
)

select
    op,
    lsn,
    r->>'$.order_id'                                       as order_id,
    r->>'$.customer_id'                                    as customer_id,
    r->>'$.status'                                         as status,
    lower(r->>'$.currency')                                as currency,
    try_cast(r->>'$.total_minor' as bigint)                as total_minor,
    r->>'$.ship_region'                                    as ship_region,
    try_cast(r->>'$.created_at' as timestamptz)            as created_at,
    try_cast(r->>'$.updated_at' as timestamptz)            as updated_at,
    case
        when j is null                          then 'unparseable_json'
        when op not in ('c', 'u', 'd', 'r')     then 'unknown_op'
        when lsn is null                        then 'missing_lsn'
        when r->>'$.order_id' is null           then 'missing_order_id'
    end as quarantine_reason,
    _raw, _bronze_row, _batch_seq, _arrived_at, _ingested_at
from parsed
