-- Retention policy for FLOW_SEEN (keep last 90 days)
-- Creates a daily scheduler job if it doesn't already exist.

DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*)
      INTO v_count
      FROM user_scheduler_jobs
     WHERE job_name = 'FLOW_SEEN_RETENTION_JOB';

    IF v_count = 0 THEN
        DBMS_SCHEDULER.CREATE_JOB(
            job_name        => 'FLOW_SEEN_RETENTION_JOB',
            job_type        => 'PLSQL_BLOCK',
            job_action      => 'BEGIN
                                    DELETE FROM TOMEHUB_FLOW_SEEN
                                    WHERE seen_at < SYSTIMESTAMP - NUMTODSINTERVAL(90, ''DAY'');
                                    COMMIT;
                                END;',
            start_date      => SYSTIMESTAMP,
            repeat_interval => 'FREQ=DAILY;BYHOUR=3;BYMINUTE=0;BYSECOND=0',
            enabled         => TRUE,
            comments        => 'Retention: delete FLOW_SEEN rows older than 90 days'
        );
    END IF;
END;
/
