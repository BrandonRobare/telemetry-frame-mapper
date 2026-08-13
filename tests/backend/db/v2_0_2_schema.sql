CREATE TABLE job_queue (
	id INTEGER NOT NULL, 
	job_type VARCHAR NOT NULL, 
	target_id INTEGER NOT NULL, 
	status VARCHAR, 
	priority INTEGER, 
	payload_json TEXT, 
	error_msg VARCHAR, 
	attempt INTEGER, 
	max_attempts INTEGER, 
	created_at DATETIME, 
	started_at DATETIME, 
	completed_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE projects (
	id INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	description TEXT, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);
CREATE TABLE target_areas (
	id INTEGER NOT NULL, 
	name VARCHAR, 
	geom_geojson TEXT, 
	created_at DATETIME, 
	notes TEXT, 
	PRIMARY KEY (id)
);
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
CREATE TABLE sessions (
	id INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	folder_path VARCHAR, 
	import_mode VARCHAR, 
	project_id INTEGER, 
	imported_at DATETIME, 
	photo_count INTEGER, 
	usable_count INTEGER, 
	notes TEXT, 
	tags TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(project_id) REFERENCES projects (id)
);
CREATE TABLE auto_import_records (
	id INTEGER NOT NULL, 
	fingerprint VARCHAR NOT NULL, 
	source_path VARCHAR NOT NULL, 
	session_id INTEGER NOT NULL, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES sessions (id)
);
CREATE TABLE defects (
	id INTEGER NOT NULL, 
	session_id INTEGER NOT NULL, 
	category VARCHAR NOT NULL, 
	severity VARCHAR, 
	note TEXT, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES sessions (id)
);
CREATE TABLE flight_entries (
	id INTEGER NOT NULL, 
	session_id INTEGER NOT NULL, 
	battery_id VARCHAR, 
	start_pct FLOAT, 
	end_pct FLOAT, 
	duration_s FLOAT, 
	notes TEXT, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES sessions (id)
);
CREATE TABLE flight_logs (
	id INTEGER NOT NULL, 
	session_id INTEGER NOT NULL, 
	filename VARCHAR, 
	filepath VARCHAR, 
	format VARCHAR, 
	point_count INTEGER, 
	log_version INTEGER, 
	aircraft_name VARCHAR, 
	aircraft_sn VARCHAR, 
	encrypted BOOLEAN, 
	uploaded_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES sessions (id)
);
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
	original_latitude FLOAT, 
	original_longitude FLOAT, 
	original_altitude_m FLOAT, 
	synced_latitude FLOAT, 
	synced_longitude FLOAT, 
	synced_altitude_m FLOAT, 
	gps_source VARCHAR, 
	yaw FLOAT, 
	gimbal_pitch FLOAT, 
	width INTEGER, 
	height INTEGER, 
	focal_length_mm FLOAT, 
	camera_make VARCHAR, 
	camera_model VARCHAR, 
	lens_model VARCHAR, 
	focal_length_35mm FLOAT, 
	digital_zoom_ratio FLOAT, 
	sharpness_score FLOAT, 
	brightness_score FLOAT, 
	flag VARCHAR, 
	usable BOOLEAN, 
	notes TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES sessions (id)
);
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
CREATE TABLE reconstructions (
	id INTEGER NOT NULL, 
	session_id INTEGER NOT NULL, 
	parent_reconstruction_id INTEGER, 
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
	ortho_path VARCHAR, 
	ortho_status VARCHAR, 
	ortho_error VARCHAR, 
	semantic_status VARCHAR, 
	semantic_error VARCHAR, 
	semantic_labels_path VARCHAR, 
	geo_transform TEXT, 
	error_msg VARCHAR, 
	started_at DATETIME, 
	completed_at DATETIME, 
	duration_s FLOAT, 
	training_metrics TEXT, 
	coverage_gaps_path VARCHAR, 
	source_session_ids TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES sessions (id), 
	FOREIGN KEY(parent_reconstruction_id) REFERENCES reconstructions (id)
);
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
CREATE TABLE defect_images (
	defect_id INTEGER NOT NULL, 
	image_id INTEGER NOT NULL, 
	PRIMARY KEY (defect_id, image_id), 
	FOREIGN KEY(defect_id) REFERENCES defects (id), 
	FOREIGN KEY(image_id) REFERENCES images (id)
);
CREATE TABLE flight_log_points (
	id INTEGER NOT NULL, 
	flight_log_id INTEGER NOT NULL, 
	timestamp DATETIME, 
	latitude FLOAT, 
	longitude FLOAT, 
	altitude_m FLOAT, 
	speed_ms FLOAT, 
	heading FLOAT, 
	roll FLOAT, 
	pitch FLOAT, 
	yaw FLOAT, 
	gimbal_pitch FLOAT, 
	gimbal_roll FLOAT, 
	gimbal_yaw FLOAT, 
	battery_voltage FLOAT, 
	battery_charge_pct FLOAT, 
	battery_temperature_c FLOAT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(flight_log_id) REFERENCES flight_logs (id)
);
CREATE TABLE footprints (
	id INTEGER NOT NULL, 
	image_id INTEGER NOT NULL, 
	geom_wkt TEXT, 
	geom_geojson TEXT, 
	ground_width_m FLOAT, 
	ground_height_m FLOAT, 
	heading_estimated BOOLEAN, 
	pitch_oblique BOOLEAN, 
	PRIMARY KEY (id), 
	FOREIGN KEY(image_id) REFERENCES images (id)
);
CREATE TABLE measurements (
	id INTEGER NOT NULL, 
	reconstruction_id INTEGER NOT NULL, 
	kind VARCHAR NOT NULL, 
	points_json TEXT NOT NULL, 
	value FLOAT, 
	unit VARCHAR, 
	label VARCHAR, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(reconstruction_id) REFERENCES reconstructions (id)
);
CREATE TABLE reconstruction_frames (
	reconstruction_id INTEGER NOT NULL, 
	image_id INTEGER NOT NULL, 
	colmap_error_px FLOAT, 
	PRIMARY KEY (reconstruction_id, image_id), 
	FOREIGN KEY(reconstruction_id) REFERENCES reconstructions (id), 
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
CREATE TABLE session_frame_selections (
	session_id INTEGER NOT NULL, 
	image_id INTEGER NOT NULL, 
	PRIMARY KEY (session_id, image_id), 
	FOREIGN KEY(session_id) REFERENCES sessions (id) ON DELETE CASCADE, 
	FOREIGN KEY(image_id) REFERENCES images (id) ON DELETE CASCADE
);
CREATE TABLE share_links (
	id INTEGER NOT NULL, 
	reconstruction_id INTEGER NOT NULL, 
	token_hash VARCHAR NOT NULL, 
	expires_at DATETIME NOT NULL, 
	password_hash TEXT, 
	revoked_at DATETIME, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(reconstruction_id) REFERENCES reconstructions (id)
);
CREATE TABLE share_link_unlock_sessions (
	id INTEGER NOT NULL, 
	share_link_id INTEGER NOT NULL, 
	token_hash VARCHAR NOT NULL, 
	expires_at DATETIME NOT NULL, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(share_link_id) REFERENCES share_links (id)
);
