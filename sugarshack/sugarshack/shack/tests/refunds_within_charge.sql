-- A charge can't be refunded for more than it captured. If this fails, a refund was
-- double-counted, or a parser is reading the wrong amount field.
with captured as (
    select charge_id, sum(amount_minor) as captured
    from {{ ref('silver_payments') }} where event_type = 'capture' group by 1
),
refunded as (
    select charge_id, sum(amount_minor) as refunded
    from {{ ref('silver_payments') }} where event_type = 'refund' group by 1
)
select * from refunded join captured using (charge_id)
where refunded > captured
