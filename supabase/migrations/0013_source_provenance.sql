-- Provenance of imported football data: where a file came from, under what licence, when it was retrieved and which version of the dataset it is.
-- All optional and supplied by the person importing; nothing is fetched or verified by the application.

alter table football_data_sources add column if not exists source_url text check (source_url is null or (char_length(source_url) <= 500 and source_url ~* '^https?://'));
alter table football_data_sources add column if not exists source_licence text check (source_licence is null or char_length(source_licence) <= 300);
alter table football_data_sources add column if not exists retrieved_on date;
alter table football_data_sources add column if not exists dataset_version text check (dataset_version is null or char_length(dataset_version) <= 60);
