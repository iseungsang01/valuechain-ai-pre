#!/bin/bash
MAX_ITERATIONS=20
ITERATION=1
TASK_FILE="RALPH_TASK.md"
LOG_FILE=".ralph/activity.log"
ERROR_LOG=".ralph/last_error.log"

echo "=== 시작: Ralph Wiggum Loop ===" | tee -a "$LOG_FILE"

# agent 명령어를 흉내내는 임시 함수 제거됨 (agent.py로 대체)

while [ $ITERATION -le $MAX_ITERATIONS ]; do
    echo -e "\n\033[0;36m=== Iteration $ITERATION ===\033[0m" | tee -a "$LOG_FILE"
    
    TEMP_PROMPT=".ralph/temp_prompt_$ITERATION.md"
    cat .ralph/guardrails.md > "$TEMP_PROMPT"
    echo -e "\n\n### 현재 태스크\n" >> "$TEMP_PROMPT"
    cat "$TASK_FILE" >> "$TEMP_PROMPT"
    
    if [ -f "$ERROR_LOG" ]; then
        echo -e "\n\n### [중요] 이전 실행 에러 피드백:\n\`\`\`" >> "$TEMP_PROMPT"
        cat "$ERROR_LOG" >> "$TEMP_PROMPT"
        echo -e "\n\`\`\`\n위 에러를 분석하고 코드를 수정하세요." >> "$TEMP_PROMPT"
    fi
    
    echo "에이전트 실행 중..."
    cat "$TEMP_PROMPT" | python agent.py
    AGENT_EXIT_CODE=$?

    if [ $AGENT_EXIT_CODE -ne 0 ]; then
        echo -e "\033[0;31m[에러] 에이전트 실행 실패 (Exit Code: $AGENT_EXIT_CODE). API 키 또는 네트워크를 확인하세요.\033[0m" | tee -a "$LOG_FILE"
        exit 1
    fi
    
    TEST_CMD=$(grep -i "test_command:" "$TASK_FILE" | sed -E 's/.*test_command:[[:space:]]*"?([^"]*)"?.*/\1/')
    
    if [ ! -z "$TEST_CMD" ]; then
        echo "테스트 검증 실행: $TEST_CMD"
        eval "$TEST_CMD" > "$ERROR_LOG" 2>&1
        TEST_RESULT=$?
        
        cat "$ERROR_LOG"
        
        if [ $TEST_RESULT -eq 0 ]; then
            echo -e "\033[0;32m[성공] 테스트 통과 및 모든 기준 만족. 루프 종료.\033[0m"
            rm -f "$ERROR_LOG"
            break
        else
            echo -e "\033[0;33m[실패] 테스트 실패. 에러 로그를 다음 루프에 전달합니다...\033[0m"
        fi
    else
        echo -e "\033[0;31m[경고] test_command를 찾을 수 없습니다.\033[0m"
        break
    fi
    
    ITERATION=$((ITERATION + 1))
done

if [ $ITERATION -gt $MAX_ITERATIONS ]; then
    echo -e "\033[0;31m[종료] 최대 이터레이션($MAX_ITERATIONS) 도달. 작업 실패.\033[0m"
fi