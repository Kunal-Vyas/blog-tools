-- Net revenue by the day customers ordered: the view product and marketing use.
--
-- A refund three weeks later changes an old day. So each run finds the order dates that
-- new data touches (a payment event, or a change to the order itself) and rebuilds just
-- those dates: delete them, insert them again. Everything else stays as it was.
--
-- Conversion uses the order-date rate for captures and refunds alike, so a full refund
-- takes an order to exactly zero. (The cash view uses the rate on the day money moved.)
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='order_date',
) }}

{%- set watermark -%}
    (select coalesce(max(_built_through_seq), 0) from {{ this }})
{%- endset %}

with affected as (
    select distinct order_date
    from {{ ref('fct_payments') }}
    where order_date is not null
    {%- if is_incremental() %}
      and _batch_seq > {{ watermark }}
    union
    select distinct (created_at at time zone '{{ var("business_tz") }}')::date
    from {{ ref('silver_orders') }}
    where _batch_seq > {{ watermark }}
    {%- endif %}
),

usd_cad as (
    select rate_date, rate from {{ ref('silver_fx_rates') }} where base = 'USD' and quote = 'CAD'
),

events as (
    select f.order_date, f.ship_region, f.order_id, f.event_type, f.currency, f.amount_minor
    from {{ ref('fct_payments') }} f
    where f.order_date in (select order_date from affected)
),

converted as (
    select e.*,
           round(e.amount_minor / 100.0
                 * case e.currency when 'cad' then 1.0 else fx.rate end, 2) as amount_cad
    from events e
    asof left join usd_cad fx on e.order_date >= fx.rate_date
),

built_through as (
    select greatest(
        (select coalesce(max(_batch_seq), 0) from {{ ref('fct_payments') }}),
        (select coalesce(max(_batch_seq), 0) from {{ ref('silver_orders') }})
    ) as seq
)

select
    order_date,
    ship_region,
    count(distinct order_id) filter (where event_type = 'capture')        as paid_orders,
    coalesce(sum(amount_cad) filter (where event_type = 'capture'), 0)::decimal(18, 2)
                                                                          as gross_cad,
    coalesce(-sum(amount_cad) filter (where event_type = 'refund'), 0)::decimal(18, 2)
                                                                          as refunds_cad,
    sum(amount_cad)::decimal(18, 2)                                       as net_cad,
    (select seq from built_through)                                       as _built_through_seq
from converted
group by all
