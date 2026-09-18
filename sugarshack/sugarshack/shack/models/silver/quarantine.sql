-- The settling tank. Rows no parser could use, with the reason, kept until someone drains
-- them: fix the parser, replay from bronze, and they flow through to silver.
{{ config(materialized='incremental', incremental_strategy='append') }}

{% for source, model in [('payments', 'stg_payment_events'), ('orders', 'stg_order_changes')] %}
select
    '{{ source }}' as source, quarantine_reason, _raw, _bronze_row,
    _batch_seq, _arrived_at, _ingested_at
from {{ ref(model) }}
where quarantine_reason is not null
{%- if is_incremental() %}
  and _batch_seq > (select coalesce(max(_batch_seq), 0) from {{ this }} where source = '{{ source }}')
{%- endif %}
{{ 'union all' if not loop.last }}
{% endfor %}
