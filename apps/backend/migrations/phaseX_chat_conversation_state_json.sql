-- Phase X: Separate structured conversation state from legacy RUNNING_SUMMARY.
DECLARE
    v_count NUMBER := 0;
BEGIN
    SELECT COUNT(*)
      INTO v_count
      FROM user_tab_columns
     WHERE table_name = 'TOMEHUB_CHAT_SESSIONS'
       AND column_name = 'CONVERSATION_STATE_JSON';

    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_CHAT_SESSIONS ADD (CONVERSATION_STATE_JSON CLOB)';
    END IF;

    SELECT COUNT(*)
      INTO v_count
      FROM user_constraints
     WHERE table_name = 'TOMEHUB_CHAT_SESSIONS'
       AND constraint_name = 'CHK_CHAT_CONV_STATE_JSON';

    IF v_count = 0 THEN
        EXECUTE IMMEDIATE '
            ALTER TABLE TOMEHUB_CHAT_SESSIONS
            ADD CONSTRAINT CHK_CHAT_CONV_STATE_JSON
            CHECK (CONVERSATION_STATE_JSON IS JSON)';
    END IF;
END;
/
