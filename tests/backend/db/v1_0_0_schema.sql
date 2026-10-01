-- Schema of a database created by v1.0.0, the last release before projects
-- (revision 0005) and before Alembic, so it has no alembic_version table.
--
-- Generated, not written by hand: backend/db from tag v1.0.0 (c8bf6b2) ran its
-- own init_db() (create_all + _ensure_sqlite_schema) on an empty SQLite file,
-- and every sqlite_master statement was dumped in creation order. Do not edit.
CREATE TABLE sessions (
	id INTEGER NOT NULL,
	name VARCHAR NOT NULL,
	folder_path VARCHAR, 
	import_mode VARCHAR, 
	imported_at DATETIME, 
	photo_count INTEGER, 
	usable_count INTEGER, 
	notes TEXT, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_sessions_id ON sessions (id);
CREATE TABLE target_areas (
	id INTEGER NOT NULL, 
	name VARCHAR, 
	geom_geojson TEXT, 
	created_at DATETIME, 
	notes TEXT, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_target_areas_id ON target_areas (id);
CREATE TABLE images (
	id INTEGER NOT NULL, 
	session_id INTEGER NOT NULL, 
	filename VARCHAR NOT NULL, 
	filepath VARCHAR NOT NULL, 
	thumb_path VARCHAR, 
	timestamp DATETIME, 
	latitude FLOAT, 
	longitude FLOAT, 
	altitude_m FLOAT, 
	gps_source VARCHAR, 
	yaw FLOAT, 
	gimbal_pitch FLOAT, 
	width INTEGER, 
	height INTEGER, 
	focal_length_mm FLOAT, 
	sharpness_score FLOAT, 
	brightness_score FLOAT, 
	flag VARCHAR, 
	usable BOOLEAN, 
	notes TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES sessions (id)
);
CREATE INDEX ix_images_id ON images (id);
CREATE TABLE flight_logs (
	id INTEGER NOT NULL, 
	session_id INTEGER NOT NULL, 
	filename VARCHAR, 
	filepath VARCHAR, 
	format VARCHAR, 
	point_count INTEGER, 
	uploaded_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES sessions (id)
);
CREATE INDEX ix_flight_logs_id ON flight_logs (id);
CREATE TABLE coverage_runs (
	id INTEGER NOT NULL, 
	target_area_id INTEGER NOT NULL, 
	session_ids TEXT, 
	total_area_m2 FLOAT, 
	covered_area_m2 FLOAT, 
	coverage_pct FLOAT, 
	gap_geojson TEXT, 
	overlap_geojson TEXT, 
	run_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(target_area_id) REFERENCES target_areas (id)
);
CREATE INDEX ix_coverage_runs_id ON coverage_runs (id);
CREATE TABLE session_log_entries (
	id INTEGER NOT NULL, 
	session_id INTEGER, 
	timestamp DATETIME, 
	event_type VARCHAR, 
	coverage_pct FLOAT, 
	photo_count INTEGER, 
	message TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES sessions (id)
);
CREATE INDEX ix_session_log_entries_id ON session_log_entries (id);
CREATE TABLE reconstructions (
	id INTEGER NOT NULL, 
	session_id INTEGER NOT NULL, 
	status VARCHAR, 
	preset VARCHAR, 
	progress_pct FLOAT, 
	step VARCHAR, 
	frames_used INTEGER, 
	frames_registered INTEGER, 
	gaussian_count INTEGER, 
	psnr FLOAT, 
	ssim FLOAT, 
	colmap_dir VARCHAR, 
	splat_path VARCHAR, 
	splat_preview_path VARCHAR, 
	splat_medium_path VARCHAR, 
	thumb_path VARCHAR, 
	pointcloud_path VARCHAR, 
	mesh_glb_path VARCHAR, 
	mesh_obj_path VARCHAR, 
	mesh_mtl_path VARCHAR, 
	mesh_status VARCHAR, 
	mesh_error VARCHAR, 
	flythrough_path VARCHAR, 
	flythrough_status VARCHAR, 
	flythrough_error VARCHAR, 
	geo_transform TEXT, 
	error_msg VARCHAR, 
	started_at DATETIME, 
	completed_at DATETIME, 
	duration_s FLOAT, 
	training_metrics TEXT, 
	coverage_gaps_path VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES sessions (id)
);
CREATE INDEX ix_reconstructions_id ON reconstructions (id);
CREATE TABLE footprints (
	id INTEGER NOT NULL, 
	image_id INTEGER NOT NULL, 
	geom_wkt TEXT, 
	geom_geojson TEXT, 
	ground_width_m FLOAT, 
	ground_height_m FLOAT, 
	heading_estimated BOOLEAN, 
	PRIMARY KEY (id), 
	FOREIGN KEY(image_id) REFERENCES images (id)
);
CREATE INDEX ix_footprints_id ON footprints (id);
CREATE TABLE flight_log_points (
	id INTEGER NOT NULL, 
	flight_log_id INTEGER NOT NULL, 
	timestamp DATETIME, 
	latitude FLOAT, 
	longitude FLOAT, 
	altitude_m FLOAT, 
	speed_ms FLOAT, 
	heading FLOAT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(flight_log_id) REFERENCES flight_logs (id)
);
CREATE INDEX ix_flight_log_points_id ON flight_log_points (id);
CREATE TABLE mission_plans (
	id INTEGER NOT NULL, 
	target_area_id INTEGER NOT NULL, 
	coverage_run_id INTEGER, 
	altitude_ft FLOAT, 
	side_overlap_pct FLOAT, 
	forward_overlap_pct FLOAT, 
	lane_spacing_ft FLOAT, 
	lane_count INTEGER, 
	total_distance_m FLOAT, 
	batteries_estimated FLOAT, 
	lanes_geojson TEXT, 
	kml_path VARCHAR, 
	gpx_path VARCHAR, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(target_area_id) REFERENCES target_areas (id), 
	FOREIGN KEY(coverage_run_id) REFERENCES coverage_runs (id)
);
CREATE INDEX ix_mission_plans_id ON mission_plans (id);
CREATE TABLE reconstruction_frames (
	reconstruction_id INTEGER NOT NULL, 
	image_id INTEGER NOT NULL, 
	colmap_error_px FLOAT, 
	PRIMARY KEY (reconstruction_id, image_id), 
	FOREIGN KEY(reconstruction_id) REFERENCES reconstructions (id), 
	FOREIGN KEY(image_id) REFERENCES images (id) ON DELETE CASCADE
);
CREATE TABLE annotations (
	id INTEGER NOT NULL, 
	reconstruction_id INTEGER NOT NULL, 
	label VARCHAR NOT NULL, 
	lat FLOAT NOT NULL, 
	lon FLOAT NOT NULL, 
	alt_m FLOAT NOT NULL, 
	color VARCHAR, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(reconstruction_id) REFERENCES reconstructions (id)
);
CREATE INDEX ix_annotations_id ON annotations (id);
CREATE TABLE session_frame_selections (
	session_id INTEGER NOT NULL, 
	image_id INTEGER NOT NULL, 
	PRIMARY KEY (session_id, image_id), 
	FOREIGN KEY(session_id) REFERENCES sessions (id) ON DELETE CASCADE, 
	FOREIGN KEY(image_id) REFERENCES images (id) ON DELETE CASCADE
);
CREATE TABLE session_comparisons (
	id INTEGER NOT NULL, 
	session_a_id INTEGER NOT NULL, 
	session_b_id INTEGER NOT NULL, 
	reconstruction_a_id INTEGER NOT NULL, 
	reconstruction_b_id INTEGER NOT NULL, 
	status VARCHAR, 
	diff_path VARCHAR, 
	error_msg VARCHAR, 
	created_at DATETIME, 
	completed_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_a_id) REFERENCES sessions (id), 
	FOREIGN KEY(session_b_id) REFERENCES sessions (id), 
	FOREIGN KEY(reconstruction_a_id) REFERENCES reconstructions (id), 
	FOREIGN KEY(reconstruction_b_id) REFERENCES reconstructions (id)
);
CREATE INDEX ix_session_comparisons_id ON session_comparisons (id);
