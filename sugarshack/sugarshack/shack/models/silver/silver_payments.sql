-- One row per payment event, however many times it was delivered.
--
-- The processor delivers at least once, so the event id is the idempotency key. Within
-- the new batches, keep the first delivery; against the table, insert only ids we have
-- never seen. Nothing is ever updated: a payment event is a fact, not a state.
{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key='event_id',
    merge_clauses={'when_not_matched': [{'action': 'insert', 'mode': 'by_name'}]},
) }}

select
    event_id, event_type, api_version, charge_id, refund_id, order_id,
    amount_minor,                       -- integer minor units (cents): money is never a float
    currency, created_at,
    _bronze_row, _batch_seq, _arrived_at, _ingested_at
from {{ ref('stg_payment_events') }}
where quarantine_reason is null
  and {{ new_batches() }}
qualify row_number() over (partition by event_id
                           order by _batch_seq, _arrived_at, _bronze_row) = 1
