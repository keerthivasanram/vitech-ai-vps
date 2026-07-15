-- Vitech AI knowledge base — normalized offer tables (Supabase / Postgres)
drop table if exists price_items cascade;
drop table if exists technical_details cascade;
drop table if exists given_data cascade;
drop table if exists documents cascade;

create table documents (
    id           text primary key,
    category     text,
    title        text,
    client       text,
    vendor       text,
    ref          text,
    doc_date     date,
    source_file  text,
    headline     text,
    price_total  numeric,
    currency     text
);

create table given_data (
    id           bigserial primary key,
    document_id  text references documents(id) on delete cascade,
    field        text,
    value        text
);

create table technical_details (
    id           bigserial primary key,
    document_id  text references documents(id) on delete cascade,
    field        text,
    value        text
);

create table price_items (
    id           bigserial primary key,
    document_id  text references documents(id) on delete cascade,
    item         text,
    amount       numeric,
    currency     text
);
