{#
  Readers list the log, not the folder.

  A bronze view selects exactly the Parquet files the manifest has committed. A file a
  crashed run left behind is invisible here even before tap.py sweeps it away. Table
  formats (Delta, Iceberg) work the same way: the transaction log decides what a table is.
#}
{% macro bronze_source(source) %}
    {%- set files = [] -%}
    {%- if execute -%}
        {%- set q -%}
            select distinct parquet
            from read_json('{{ var("lake") }}/bronze/_manifest.jsonl',
                           columns = {source: 'VARCHAR', parquet: 'VARCHAR'})
            where source = '{{ source }}' and parquet is not null
            order by 1
        {%- endset -%}
        {%- set files = run_query(q).columns[0].values() -%}
    {%- endif %}
    {%- if files | length > 0 %}
    select *, _landing_file || ':' || _line as _bronze_row
    from read_parquet([
        {%- for f in files %}
        '{{ var("lake") }}/{{ f }}'{{ "," if not loop.last }}
        {%- endfor %}
    ])
    {%- else %}
    select null::varchar as _raw, null::varchar as _landing_file, null::integer as _line,
           null::varchar as _file_sha256, null::timestamptz as _arrived_at,
           null::varchar as _batch_id, null::bigint as _batch_seq,
           null::timestamptz as _ingested_at, null::varchar as _bronze_row
    where false
    {%- endif %}
{% endmacro %}


{# Only rows from bronze batches this model hasn't processed yet. #}
{% macro new_batches(column='_batch_seq') %}
    {%- if is_incremental() -%}
    {{ column }} > (select coalesce(max(_batch_seq), 0) from {{ this }})
    {%- else -%}
    true
    {%- endif -%}
{% endmacro %}
