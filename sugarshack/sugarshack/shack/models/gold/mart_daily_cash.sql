-- Money in and out by processor day and currency. The table finance reconciles, and the
-- one grade.py weighs against the processor's settlement report, cent for cent.

select
    processor_date,
    currency,
    coalesce(sum(amount_minor) filter (where event_type = 'capture'), 0)::bigint  as captured_minor,
    coalesce(-sum(amount_minor) filter (where event_type = 'refund'), 0)::bigint  as refunded_minor,
    sum(amount_minor)::bigint                                                      as net_minor,
    count(*) filter (where event_type = 'capture')                                 as captures,
    count(*) filter (where event_type = 'refund')                                  as refunds,
    sum(amount_cad)::decimal(18, 2)                                                as net_cad
from {{ ref('fct_payments') }}
group by all
