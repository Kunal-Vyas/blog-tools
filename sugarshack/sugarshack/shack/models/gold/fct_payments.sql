-- Every money movement, signed, with both of its dates and its CAD value.
--
--   processor_date  the UTC day the processor booked it. Settlement reports use this,
--                   so reconciliation must too.
--   order_date      the Halifax day the customer ordered. Product and marketing use this.
--
-- USD converts at the rate for the processor date: when the money moved. Weekends and
-- holidays have no rate, so the ASOF join takes the latest rate on or before that day,
-- and fx_rate_date says which one it used.

with payments as (
    select *, (created_at at time zone 'UTC')::date as processor_date
    from {{ ref('silver_payments') }}
),

usd_cad as (
    select rate_date, rate
    from {{ ref('silver_fx_rates') }}
    where base = 'USD' and quote = 'CAD'
),

orders as (
    select order_id, ship_region,
           (created_at at time zone '{{ var("business_tz") }}')::date as order_date
    from {{ ref('silver_orders') }}
    where not is_deleted
)

select
    p.event_id,
    p.event_type,
    p.charge_id,
    p.refund_id,
    p.order_id,
    p.currency,
    case p.event_type when 'capture' then p.amount_minor else -p.amount_minor end as amount_minor,
    p.created_at,
    p.processor_date,
    o.order_date,
    o.ship_region,
    case p.currency when 'cad' then p.processor_date else fx.rate_date end   as fx_rate_date,
    case p.currency when 'cad' then 1.0 else fx.rate end::decimal(12, 6)     as fx_rate,
    round(case p.event_type when 'capture' then 1 else -1 end
          * p.amount_minor / 100.0
          * case p.currency when 'cad' then 1.0 else fx.rate end, 2)::decimal(18, 2)
                                                                             as amount_cad,
    p._batch_seq,
    p._ingested_at
from payments p
asof left join usd_cad fx
    on p.processor_date >= fx.rate_date
left join orders o
    using (order_id)
