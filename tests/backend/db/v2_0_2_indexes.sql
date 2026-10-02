-- Index DDL omitted from v2_0_2_schema.sql, captured by running init_db()
-- from tag v2.0.2 (08440fe), never from current models. Frozen.
CREATE INDEX ix_projects_id ON projects (id);
CREATE INDEX ix_target_areas_id ON target_areas (id);
CREATE INDEX ix_job_queue_id ON job_queue (id);
CREATE INDEX ix_sessions_id ON sessions (id);
CREATE INDEX ix_coverage_runs_id ON coverage_runs (id);
CREATE INDEX ix_images_id ON images (id);
CREATE INDEX ix_flight_logs_id ON flight_logs (id);
CREATE INDEX ix_flight_entries_id ON flight_entries (id);
CREATE INDEX ix_mission_plans_id ON mission_plans (id);
CREATE INDEX ix_session_log_entries_id ON session_log_entries (id);
CREATE INDEX ix_reconstructions_id ON reconstructions (id);
CREATE INDEX ix_defects_id ON defects (id);
CREATE UNIQUE INDEX ix_auto_import_records_fingerprint ON auto_import_records (fingerprint);
CREATE INDEX ix_auto_import_records_id ON auto_import_records (id);
CREATE INDEX ix_footprints_id ON footprints (id);
CREATE INDEX ix_flight_log_points_id ON flight_log_points (id);
CREATE UNIQUE INDEX ix_share_links_token_hash ON share_links (token_hash);
CREATE INDEX ix_share_links_id ON share_links (id);
CREATE INDEX ix_annotations_id ON annotations (id);
CREATE INDEX ix_measurements_id ON measurements (id);
CREATE INDEX ix_session_comparisons_id ON session_comparisons (id);
CREATE UNIQUE INDEX ix_share_link_unlock_sessions_token_hash ON share_link_unlock_sessions (token_hash);
CREATE INDEX ix_share_link_unlock_sessions_id ON share_link_unlock_sessions (id);
