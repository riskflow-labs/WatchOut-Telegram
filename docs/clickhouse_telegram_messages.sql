CREATE DATABASE IF NOT EXISTS watchout_telegram;

CREATE TABLE IF NOT EXISTS watchout_telegram.telegram_messages
(
    id String,
    message_uid String,
    channel LowCardinality(String),
    source String,
    source_id String,
    source_type LowCardinality(String),
    sub_channel LowCardinality(String),
    message_id String,
    event_time DateTime64(3, 'UTC'),
    insert_time DateTime64(3, 'UTC'),
    sender_id String,
    sender_username String,
    sender_name String,
    content String,
    content_md5 String,
    data_id String,
    similar_id String,
    message_kind LowCardinality(String),
    media_type LowCardinality(String),
    media_count UInt16,
    links Array(String),
    views_count UInt64,
    replies_count UInt64,
    forwards_count UInt64,
    risk_level UInt8,
    score UInt16,
    hit UInt8,
    status LowCardinality(String)
)
ENGINE = ReplacingMergeTree(insert_time)
PARTITION BY toYYYYMM(event_time)
ORDER BY (source_id, message_id, message_uid);
