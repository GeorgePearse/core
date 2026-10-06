-- ClickHouse Query: Fetch test split frames from metals_conveyor dataset
-- Source: modal_app.py:125
-- Execution time: ~14.8 seconds
-- Results: 112 frame events
-- Date range: 2025-08-20 to 2025-11-13

SELECT distinct on (frame_uri)
       frame_uri,
       toString(generateUUIDv4()) AS id,
       updated_timestamp          AS event_time,
       image_width                AS width,
       image_height               AS height,
       -- placeholder camera id for machine learning data
       202                        AS camera_id
FROM psql.labelled_datasets FINAL
WHERE dataset_name = 'metals_conveyor'
  and _peerdb_is_deleted = 0
  and training_split = 'test'
