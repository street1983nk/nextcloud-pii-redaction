<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Migration;

use Closure;
use OCP\DB\ISchemaWrapper;
use OCP\DB\Types;
use OCP\Migration\IOutput;
use OCP\Migration\SimpleMigrationStep;

/**
 * The three tables of the PHP app, all of them in this first migration, so no
 * later phase has to add a column that could carry clear text.
 *
 * pii_jobs holds one row per job: ids, the etag the job is bound to, numbers
 * and words from the closed lists in OCA\PiiRedaction\Model. pii_job_events is
 * the minimal history (who did what, when, as a word from a closed list).
 * pii_slot has exactly one row; a conditional UPDATE on it is the rule "one
 * analyze or apply job at a time" on SQLite, MySQL/MariaDB and PostgreSQL
 * alike (JobMapper::claimNext).
 *
 * There is deliberately no column for a file name, a path, a mime type or any
 * text of a document (success criterion 5 of phase 1): the file name is looked
 * up from file_id in the user's context whenever it is needed, and never
 * stored. backend/tests/test_php_schema.py holds the column names to that.
 *
 * The class name and the file name are identical to the character: Nextcloud
 * loads migrations by file name, a mismatch means the step silently never runs.
 */
final class Version000100Date20261107000000 extends SimpleMigrationStep {
	/**
	 * Every table is guarded by hasTable(), so a replay after a failed upgrade
	 * is a no-op instead of an exception.
	 */
	public function changeSchema(IOutput $output, Closure $schemaClosure, array $options): ?ISchemaWrapper {
		/** @var ISchemaWrapper $schema */
		$schema = $schemaClosure();
		$changed = false;

		if (!$schema->hasTable('pii_jobs')) {
			$table = $schema->createTable('pii_jobs');

			$table->addColumn('id', Types::BIGINT, ['autoincrement' => true, 'notnull' => true, 'length' => 64]);
			$table->addColumn('file_id', Types::BIGINT, ['notnull' => true, 'length' => 64]);
			$table->addColumn('initiator_uid', Types::STRING, ['notnull' => true, 'length' => 64]);
			// The etag the job was started on. Every request compares the live
			// etag against it; a different one makes the job stale.
			$table->addColumn('file_etag', Types::STRING, ['notnull' => true, 'length' => 40]);
			// Lengths follow the longest word of the matching enum, checked by
			// ModelTest and test_php_schema.py.
			$table->addColumn('mode', Types::STRING, ['notnull' => true, 'length' => 16]);
			$table->addColumn('lang', Types::STRING, ['notnull' => true, 'length' => 8]);
			$table->addColumn('status', Types::STRING, ['notnull' => true, 'length' => 16]);
			$table->addColumn('reason', Types::STRING, ['notnull' => false, 'length' => 32]);
			$table->addColumn('task', Types::STRING, ['notnull' => false, 'length' => 16]);
			$table->addColumn('stage', Types::STRING, ['notnull' => false, 'length' => 16]);
			$table->addColumn('pages_done', Types::INTEGER, ['notnull' => false]);
			$table->addColumn('pages_total', Types::INTEGER, ['notnull' => false]);
			// The lease: a random token and a Unix second from ITimeFactory.
			// lease_until <= now means free; 0 is the free mark of a new row.
			$table->addColumn('claim_token', Types::STRING, ['notnull' => false, 'length' => 64]);
			$table->addColumn('lease_until', Types::BIGINT, ['notnull' => true, 'default' => 0, 'length' => 64]);
			$table->addColumn('attempts', Types::SMALLINT, ['notnull' => true, 'default' => 0]);
			$table->addColumn('revision', Types::INTEGER, ['notnull' => false]);
			$table->addColumn('revision_hash', Types::STRING, ['notnull' => false, 'length' => 64]);
			$table->addColumn('output_sha256', Types::STRING, ['notnull' => false, 'length' => 64]);
			$table->addColumn('output_size', Types::BIGINT, ['notnull' => false, 'length' => 64]);
			$table->addColumn('output_file_id', Types::BIGINT, ['notnull' => false, 'length' => 64]);
			// Pixel size of page 1, for the width and height of the review image.
			$table->addColumn('image_width', Types::INTEGER, ['notnull' => false]);
			$table->addColumn('image_height', Types::INTEGER, ['notnull' => false]);
			$table->addColumn('created_at', Types::BIGINT, ['notnull' => true, 'length' => 64]);
			$table->addColumn('updated_at', Types::BIGINT, ['notnull' => true, 'length' => 64]);
			$table->addColumn('expires_at', Types::BIGINT, ['notnull' => true, 'length' => 64]);

			$table->setPrimaryKey(['id'], 'pii_jobs_pk');
			$table->addIndex(['file_id'], 'pii_jobs_file');
			$table->addIndex(['task', 'status', 'id'], 'pii_jobs_queue');
			$table->addIndex(['initiator_uid'], 'pii_jobs_uid');
			$changed = true;
		}

		if (!$schema->hasTable('pii_job_events')) {
			$table = $schema->createTable('pii_job_events');

			$table->addColumn('id', Types::BIGINT, ['autoincrement' => true, 'notnull' => true, 'length' => 64]);
			$table->addColumn('job_id', Types::BIGINT, ['notnull' => true, 'length' => 64]);
			$table->addColumn('uid', Types::STRING, ['notnull' => true, 'length' => 64]);
			// A word from Status, Subject or placeholder_requested, checked by
			// JobEventMapper::record before it is written.
			$table->addColumn('action', Types::STRING, ['notnull' => true, 'length' => 32]);
			$table->addColumn('at', Types::BIGINT, ['notnull' => true, 'length' => 64]);

			$table->setPrimaryKey(['id'], 'pii_events_pk');
			$table->addIndex(['job_id'], 'pii_events_job');
			$changed = true;
		}

		if (!$schema->hasTable('pii_slot')) {
			$table = $schema->createTable('pii_slot');

			// Always 1. JobMapper::ensureSlot() inserts the row.
			$table->addColumn('id', Types::SMALLINT, ['notnull' => true]);
			$table->addColumn('job_id', Types::BIGINT, ['notnull' => false, 'length' => 64]);
			$table->addColumn('claim_token', Types::STRING, ['notnull' => false, 'length' => 64]);
			$table->addColumn('lease_until', Types::BIGINT, ['notnull' => true, 'default' => 0, 'length' => 64]);

			$table->setPrimaryKey(['id'], 'pii_slot_pk');
			$changed = true;
		}

		return $changed ? $schema : null;
	}
}
