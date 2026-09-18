{#
  One entry per payment API version the pipeline understands. Each field is a SQL
  expression over `j`, the parsed JSON event.

  Supporting a new version means adding an entry here and replaying from bronze. Until
  then, events in that version are quarantined, never guessed at.
#}
{% macro payment_parsers() %}
    {{ return({
        "2025-11-01": {
            "charge_id": "j->>'$.data.object.id'",
            "refund_id": "j->>'$.data.object.refund.id'",
            "order_id":  "j->>'$.data.object.order_id'",
            "amount":    "coalesce(j->>'$.data.object.refund.amount',
                                   j->>'$.data.object.amount')",
            "currency":  "j->>'$.data.object.currency'",
        },
        "2026-08-01": {
            "charge_id": "coalesce(j->>'$.data.object.charge', j->>'$.data.object.id')",
            "refund_id": "case when j->>'$.data.object.object' = 'refund'
                                then j->>'$.data.object.id' end",
            "order_id":  "j->>'$.data.object.metadata.order_id'",
            "amount":    "j->>'$.data.object.amount.value'",
            "currency":  "j->>'$.data.object.amount.currency'",
        },
    }) }}
{% endmacro %}


{% macro enabled_parsers() %}
    {{ return(var('payment_parsers').split(',') | map('trim') | list) }}
{% endmacro %}


{# CASE api_version WHEN <v> THEN <this field's expression in v> ... END, enabled versions only #}
{% macro parse(field) %}
    {%- set all = payment_parsers() -%}
    case api_version
    {%- for version in enabled_parsers() if version in all %}
        when '{{ version }}' then {{ all[version][field] }}
    {%- endfor %}
    end
{%- endmacro %}
