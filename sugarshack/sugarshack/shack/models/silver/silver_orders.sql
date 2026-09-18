-- The current state of every order, folded from its change log.
--
-- The rule that makes this correct: the newest change is the one with the highest LSN,
-- not the one that arrived last. Late and replayed events arrive after newer ones all the
-- time, so the merge only overwrites a row when the incoming LSN is higher.
-- Deletes are kept as tombstones (is_deleted) so a late update can't resurrect the row.
{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key='order_id',
    merge_update_condition='DBT_INTERNAL_SOURCE._lsn > DBT_INTERNAL_DEST._lsn',
) }}

select
    order_id, customer_id, status, currency, total_minor, ship_region,
    created_at, updated_at,
    op = 'd'  as is_deleted,
    lsn       as _lsn,
    _batch_seq, _arrived_at, _ingested_at
from {{ ref('stg_order_changes') }}
where quarantine_reason is null
  and {{ new_batches() }}
qualify row_number() over (partition by order_id order by lsn desc) = 1
