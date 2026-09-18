-- Daily USD/CAD. The bank sometimes republishes a day; the latest arrival wins.
{{ config(materialized='table') }}

with parsed as (
    select
        try_cast(_raw::json->>'$.rate_date' as date)      as rate_date,
        _raw::json->>'$.base'                              as base,
        _raw::json->>'$.quote'                             as quote,
        try_cast(_raw::json->>'$.rate' as decimal(12, 6)) as rate,
        _landing_file, _arrived_at, _batch_seq
    from {{ ref('bronze_fx_rates') }}
)

select * from parsed
where rate_date is not null and rate > 0
qualify row_number() over (partition by rate_date, base, quote
                           order by _arrived_at desc, _batch_seq desc) = 1
