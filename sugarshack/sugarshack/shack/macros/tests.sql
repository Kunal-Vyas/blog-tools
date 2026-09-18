{# Generic test: every value is strictly positive. #}
{% test positive(model, column_name) %}
    select * from {{ model }} where {{ column_name }} <= 0
{% endtest %}


{# Generic test: no two rows share the same values in these columns. #}
{% test unique_combination(model, columns) %}
    select {{ columns | join(', ') }}, count(*) as n
    from {{ model }}
    group by all
    having count(*) > 1
{% endtest %}
