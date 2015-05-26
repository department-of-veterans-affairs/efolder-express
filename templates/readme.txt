README
======

This is the contents of the eFolder for file number: {{ status.file_number }}.

{% for doc in status.documents %}
{{ doc.filename }}
{% if doc.filename %}{{ '-' * doc.filename|length() }}{% endif %}

Document type: {{ document_types.get(doc.doc_type|int(), doc.doc_type)|safe }}
Received at: {{ doc.received_at }}
Source: {{ doc.source }}
{% endfor %}
