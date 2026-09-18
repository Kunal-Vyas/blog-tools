-- Paid orders not yet shipped, by how long since the order last changed. The warehouse's
-- morning list. "Paid" here is the order's current state, folded by LSN in silver.

with waiting as (
    select
        order_id,
        ship_region,
        updated_at as last_change_at,
        date_diff('hour', updated_at, '{{ var("as_of") }}'::timestamptz) as hours_waiting
    from {{ ref('silver_orders') }}
    where status = 'paid'
      and not is_deleted
)

select
    case
        when hours_waiting < 24 then '1. under 24h'
        when hours_waiting < 48 then '2. 24-48h'
        when hours_waiting < 72 then '3. 48-72h'
        else                         '4. over 72h'
    end                  as waiting,
    count(*)             as orders,
    min(last_change_at)  as oldest_change_at
from waiting
group by all
order by waiting
