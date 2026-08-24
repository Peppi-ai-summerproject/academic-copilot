BEGIN;

-- A legacy deployment created tutor_meetings before the current repository
-- contract was introduced.  Upgrade it in place: no row or legacy column is
-- removed, and values that cannot be derived truthfully remain NULL.
ALTER TABLE tutor_meetings
    ADD COLUMN IF NOT EXISTS tutor_id INTEGER NULL,
    ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS legacy_status TEXT NULL;

-- Preserve the exact pre-migration status before canonicalizing recognized
-- values.  On an already-current database this records nothing.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'tutor_meetings'
          AND column_name = 'meeting_date'
    ) THEN
        UPDATE tutor_meetings
        SET legacy_status = status
        WHERE legacy_status IS NULL;

        -- meeting_date is the only truthful scheduling evidence in the legacy
        -- model.  Its DATE precision is retained as midnight UTC.  It is not
        -- evidence of when a meeting completed or was cancelled.
        UPDATE tutor_meetings
        SET scheduled_at = meeting_date::date::timestamp AT TIME ZONE 'UTC'
        WHERE scheduled_at IS NULL
          AND meeting_date IS NOT NULL;

    END IF;
END $$;

DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'tutor_meetings'
          AND column_name = 'meeting_date'
    ) THEN
        FOR constraint_name IN
            SELECT con.conname
            FROM pg_constraint AS con
            WHERE con.conrelid = 'tutor_meetings'::regclass
              AND con.contype = 'c'
              AND pg_get_constraintdef(con.oid) ILIKE '%status%'
        LOOP
            EXECUTE format(
                'ALTER TABLE tutor_meetings DROP CONSTRAINT %I',
                constraint_name
            );
        END LOOP;

        ALTER TABLE tutor_meetings ALTER COLUMN status DROP NOT NULL;

        UPDATE tutor_meetings
        SET status = CASE UPPER(BTRIM(status))
            WHEN 'SCHEDULED' THEN 'SCHEDULED'
            WHEN 'COMPLETED' THEN 'COMPLETED'
            WHEN 'MISSED' THEN 'MISSED'
            WHEN 'CANCELLED' THEN 'CANCELLED'
            WHEN 'CANCELED' THEN 'CANCELLED'
            ELSE NULL
        END;
    END IF;
END $$;

-- Do not infer tutor ownership from current assignments: an assignment does
-- not prove who attended a historical meeting.  Add the FK only if absent.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint AS con
        WHERE con.conrelid = 'tutor_meetings'::regclass
          AND con.contype = 'f'
          AND con.conkey = ARRAY[
              (SELECT attnum FROM pg_attribute
               WHERE attrelid = 'tutor_meetings'::regclass
                 AND attname = 'tutor_id')
          ]::smallint[]
    ) THEN
        ALTER TABLE tutor_meetings
            ADD CONSTRAINT fk_tutor_meetings_tutor_id
            FOREIGN KEY (tutor_id) REFERENCES tutors(id) ON DELETE RESTRICT;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_tutor_meetings_student_scheduled_at
    ON tutor_meetings (student_id, scheduled_at);
CREATE INDEX IF NOT EXISTS ix_tutor_meetings_tutor_scheduled_at
    ON tutor_meetings (tutor_id, scheduled_at);

-- NOT VALID preserves historical rows whose legacy data cannot truthfully
-- supply tutor/completion/cancellation facts, while enforcing the canonical
-- status/timestamp relationship for new and subsequently changed rows.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'tutor_meetings_status_timestamps_check'
          AND conrelid = 'tutor_meetings'::regclass
    ) THEN
        ALTER TABLE tutor_meetings
            ADD CONSTRAINT tutor_meetings_status_timestamps_check CHECK (
                (status = 'COMPLETED' AND completed_at IS NOT NULL
                    AND completed_at >= scheduled_at AND cancelled_at IS NULL)
                OR (status = 'CANCELLED' AND completed_at IS NULL
                    AND cancelled_at IS NOT NULL)
                OR (status IN ('SCHEDULED', 'MISSED')
                    AND completed_at IS NULL AND cancelled_at IS NULL)
            ) NOT VALID;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'tutor_meetings_required_canonical_fields_check'
          AND conrelid = 'tutor_meetings'::regclass
    ) THEN
        ALTER TABLE tutor_meetings
            ADD CONSTRAINT tutor_meetings_required_canonical_fields_check
            CHECK (
                tutor_id IS NOT NULL
                AND status IS NOT NULL
                AND scheduled_at IS NOT NULL
            ) NOT VALID;
    END IF;
END $$;

COMMENT ON COLUMN tutor_meetings.legacy_status IS
    'Exact status preserved from the pre-011 tutor_meetings schema; NULL for native canonical rows.';

COMMIT;
