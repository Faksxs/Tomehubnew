-- Phase X: Chat Retention (90 days default)
-- Run periodically via DBMS_SCHEDULER or external cron.

-- Delete old chat messages
DELETE FROM TOMEHUB_CHAT_MESSAGES
WHERE CREATED_AT < (SYSDATE - 90);

-- Delete empty sessions older than retention window
DELETE FROM TOMEHUB_CHAT_SESSIONS s
WHERE s.UPDATED_AT < (SYSDATE - 90)
  AND NOT EXISTS (
    SELECT 1 FROM TOMEHUB_CHAT_MESSAGES m
    WHERE m.SESSION_ID = s.ID
  );

COMMIT;

-- Optional: Scheduler job (run monthly). Uncomment to enable.
-- BEGIN
--   DBMS_SCHEDULER.CREATE_JOB(
--     job_name        => 'TOMEHUB_CHAT_RETENTION_JOB',
--     job_type        => 'PLSQL_BLOCK',
--     job_action      => 'BEGIN
--                          DELETE FROM TOMEHUB_CHAT_MESSAGES WHERE CREATED_AT < (SYSDATE - 90);
--                          DELETE FROM TOMEHUB_CHAT_SESSIONS s
--                          WHERE s.UPDATED_AT < (SYSDATE - 90)
--                            AND NOT EXISTS (SELECT 1 FROM TOMEHUB_CHAT_MESSAGES m WHERE m.SESSION_ID = s.ID);
--                          COMMIT;
--                        END;',
--     start_date      => SYSTIMESTAMP,
--     repeat_interval => 'FREQ=MONTHLY;BYMONTHDAY=1;BYHOUR=2;BYMINUTE=0;BYSECOND=0',
--     enabled         => TRUE
--   );
-- END;
-- /
