*** Settings ***
Documentation     Robot CI suite for exam-api with LocalStack.
Library           Collections
Library           RequestsLibrary
Library           String
Library           Process
Library           OperatingSystem
Suite Setup       Prepare Authenticated Context
Suite Teardown    Cleanup Created Users Best Effort

*** Variables ***
${BASE_URL}           %{BASE_URL=http://localhost:8000}
${ADMIN_EMAIL}        %{ADMIN_EMAIL=}
${ADMIN_PASSWORD}     %{ADMIN_PASSWORD=}
${TEACHER_PASSWORD}   Tc!2026RobotStrongPass9
${STUDENT_PASSWORD}   St!2026RobotStrongPass9
${REGISTER_EMAIL}     %{REGISTER_EMAIL=}
${INVITED_STUDENT_EMAIL}    %{INVITED_STUDENT_EMAIL=}

# Optional Cognito endpoint override (set for LocalStack, leave empty for real AWS).
${COGNITO_ENDPOINT_URL}    %{COGNITO_ENDPOINT_URL=}
${AWS_ACCESS_KEY_ID}       %{AWS_ACCESS_KEY_ID=}
${AWS_SECRET_ACCESS_KEY}   %{AWS_SECRET_ACCESS_KEY=}
${AWS_SESSION_TOKEN}       %{AWS_SESSION_TOKEN=}
${AWS_REGION}              %{AWS_REGION=eu-west-1}
${CREATE_COGNITO_USER_POOL}             %{CREATE_COGNITO_USER_POOL=false}
${DELETE_COGNITO_USER_POOL_ON_TEARDOWN}    %{DELETE_COGNITO_USER_POOL_ON_TEARDOWN=false}
${COGNITO_USER_POOL_ID}    %{COGNITO_USER_POOL_ID=}
${COGNITO_APP_CLIENT_ID}   %{COGNITO_APP_CLIENT_ID=}
${CREATED_COGNITO_USER_POOL_ID}    %{CREATED_COGNITO_USER_POOL_ID=}

*** Test Cases ***
Login Teacher Wrong Password Returns 401
    [Documentation]    Mirrors "Login Teacher — 401 Unauthorized" from docs/api.http.
    ${payload}=    Create Dictionary    email=${ADMIN_EMAIL}    password=WrongPassword1
    ${response}=    POST On Session    exam_api    /auth/login    json=${payload}    expected_status=any
    Should Be Equal As Integers    ${response.status_code}    401

Create Exam Without Token Returns 401
    [Documentation]    Mirrors "Create Exam — 401 Unauthorized (no token)" from docs/api.http.
    ${payload}=    Create Dictionary    title=Sans token
    ${response}=    POST On Session    exam_api    /exams    json=${payload}    expected_status=any
    Should Be Equal As Integers    ${response.status_code}    401

Register Teacher Returns 201
    [Documentation]    Mirrors "Register Teacher — 201 Created" from docs/api.http.
    ${new_email}=    Build Unique Teacher Email
    ${payload}=    Create Dictionary
    ...    email=${new_email}
    ...    password=${TEACHER_PASSWORD}
    ...    full_name=Robot Teacher
    ${response}=    POST On Session    exam_api    /auth/register    json=${payload}    headers=${ADMIN_HEADERS}    expected_status=any
    Should Be Equal As Integers    ${response.status_code}    201
    ${body}=    Evaluate    $response.json()
    Should Not Be Empty    ${body["teacher_id"]}
    Should Be Equal    ${body["email"]}    ${new_email}

Teacher Can Create And List Exam
    [Documentation]    Mirrors create/list/get exam endpoints from docs/api.http.
    ${payload}=    Create Dictionary
    ...    title=Mathematiques - Terminale S1
    ...    description=Controle final du semestre
    ...    subject=Mathematiques
    ${create_response}=    POST On Session    exam_api    /exams    json=${payload}    headers=${TEACHER_HEADERS}    expected_status=any
    Should Be Equal As Integers    ${create_response.status_code}    201
    ${create_body}=    Evaluate    $create_response.json()
    ${exam_id}=    Set Variable    ${create_body["exam_id"]}
    Set Suite Variable    ${EXAM_ID}    ${exam_id}

    ${list_response}=    GET On Session    exam_api    /exams    headers=${TEACHER_HEADERS}    expected_status=any
    Should Be Equal As Integers    ${list_response.status_code}    200

    ${detail_response}=    GET On Session    exam_api    /exams/${EXAM_ID}    headers=${TEACHER_HEADERS}    expected_status=any
    Should Be Equal As Integers    ${detail_response.status_code}    200
    ${detail_body}=    Evaluate    $detail_response.json()
    Should Be Equal    ${detail_body["exam_id"]}    ${EXAM_ID}

Teacher Can Add And List Students
    [Documentation]    Mirrors add/list students endpoints from docs/api.http.
    ${student_1}=    Create Dictionary
    ...    nom=Durand
    ...    prenom=Claire
    ...    classe=TES1
    ...    email=claire.durand+robot@lycee.fr
    ${student_2}=    Create Dictionary
    ...    nom=Martin
    ...    prenom=Hugo
    ...    classe=TES1
    ...    email=${None}
    ${students}=    Create List    ${student_1}    ${student_2}

    ${add_response}=    POST On Session    exam_api    /exams/${EXAM_ID}/students    json=${students}    headers=${TEACHER_HEADERS}    expected_status=any
    Should Be Equal As Integers    ${add_response.status_code}    201

    ${list_students_response}=    GET On Session    exam_api    /exams/${EXAM_ID}/students    headers=${TEACHER_HEADERS}    expected_status=any
    Should Be Equal As Integers    ${list_students_response.status_code}    200
    ${students_body}=    Evaluate    $list_students_response.json()
    ${items}=    Set Variable    ${students_body["items"]}
    Length Should Be    ${items}    2

Teacher Can Invite Student And Student Scope Is Accessible
    [Documentation]    Covers invite endpoint + persistence via student login/scope endpoint.
    ${student_email}=    Build Unique Student Email
    ${invite_payload}=    Create Dictionary    student_email=${student_email}
    ${invite_response}=    POST On Session    exam_api    /exams/${EXAM_ID}/students/student-robot/invite    json=${invite_payload}    headers=${TEACHER_HEADERS}    expected_status=any
    Should Be Equal As Integers    ${invite_response.status_code}    200
    ${invite_body}=    Evaluate    $invite_response.json()
    Should Not Be Empty    ${invite_body["student_id"]}
    ${student_id}=    Set Variable    ${invite_body["student_id"]}
    Set Suite Variable    ${INVITED_STUDENT_EMAIL}    ${student_email}
    Set Suite Variable    ${INVITED_STUDENT_ID}    ${student_id}

    ${pool_id}=    Get Cognito User Pool Id
    Should Not Be Empty    ${pool_id}
    ${set_password_result}=    Run Cognito Aws Cli
    ...    cognito-idp admin-set-user-password --user-pool-id ${pool_id} --username "${student_email}" --password "${STUDENT_PASSWORD}" --permanent
    Should Be Equal As Integers    ${set_password_result.rc}    0

    ${student_login_payload}=    Create Dictionary    email=${student_email}    password=${STUDENT_PASSWORD}
    ${student_login_response}=    POST On Session    exam_api    /auth/student-login    json=${student_login_payload}    expected_status=any
    Should Be Equal As Integers    ${student_login_response.status_code}    200
    ${student_login_body}=    Evaluate    $student_login_response.json()
    Should Not Be Empty    ${student_login_body["access_token"]}

    ${student_headers}=    Create Dictionary    Authorization=Bearer ${student_login_body["access_token"]}
    ${scope_response}=    GET On Session    exam_api    /exams/${EXAM_ID}/students/${student_id}/scope    headers=${student_headers}    expected_status=any
    Should Be Equal As Integers    ${scope_response.status_code}    200
    ${scope_body}=    Evaluate    $scope_response.json()
    Should Be Equal    ${scope_body["student_id"]}    ${student_id}
    Should Be Equal    ${scope_body["exam_id"]}    ${EXAM_ID}

*** Keywords ***
Prepare Authenticated Context
    Bootstrap Cognito User Pool If Requested
    Should Not Be Empty    ${ADMIN_EMAIL}
    Should Not Be Empty    ${ADMIN_PASSWORD}
    Create Session    exam_api    ${BASE_URL}
    ${admin_payload}=    Create Dictionary    email=${ADMIN_EMAIL}    password=${ADMIN_PASSWORD}
    ${admin_login_response}=    POST On Session    exam_api    /auth/login    json=${admin_payload}    expected_status=any
    Should Be Equal As Integers    ${admin_login_response.status_code}    200
    ${admin_login_body}=    Evaluate    $admin_login_response.json()
    ${admin_token}=    Set Variable    ${admin_login_body["access_token"]}
    ${admin_headers}=    Create Dictionary    Authorization=Bearer ${admin_token}
    Set Suite Variable    ${ADMIN_HEADERS}    ${admin_headers}

    ${register_email}=    Build Unique Teacher Email
    Set Suite Variable    ${REGISTER_EMAIL}    ${register_email}

    ${register_payload}=    Create Dictionary
    ...    email=${REGISTER_EMAIL}
    ...    password=${TEACHER_PASSWORD}
    ...    full_name=Robot Teacher
    ${register_response}=    POST On Session    exam_api    /auth/register    json=${register_payload}    headers=${ADMIN_HEADERS}    expected_status=any
    Should Be Equal As Integers    ${register_response.status_code}    201

    ${teacher_login_payload}=    Create Dictionary    email=${REGISTER_EMAIL}    password=${TEACHER_PASSWORD}
    ${teacher_login_response}=    POST On Session    exam_api    /auth/login    json=${teacher_login_payload}    expected_status=any
    Should Be Equal As Integers    ${teacher_login_response.status_code}    200
    ${teacher_login_body}=    Evaluate    $teacher_login_response.json()
    ${teacher_token}=    Set Variable    ${teacher_login_body["access_token"]}
    ${teacher_headers}=    Create Dictionary    Authorization=Bearer ${teacher_token}
    Set Suite Variable    ${TEACHER_HEADERS}    ${teacher_headers}

Build Unique Teacher Email
    ${epoch}=    Evaluate    __import__("time").time_ns()
    ${email}=    Catenate    SEPARATOR=    robot-teacher-    ${epoch}    @passmail.net
    RETURN    ${email}

Build Unique Student Email
    ${epoch}=    Evaluate    __import__("time").time_ns()
    ${email}=    Catenate    SEPARATOR=    robot-student-    ${epoch}    @passmail.net
    RETURN    ${email}


Cleanup Created Users Best Effort
    # Best-effort cleanup; do not make test results fail because cleanup failed.
    ${pool_id}=    Get Cognito User Pool Id
    Run Keyword And Ignore Error    Delete Cognito User Best Effort    ${pool_id}    ${REGISTER_EMAIL}
    Run Keyword And Ignore Error    Delete Cognito User Best Effort    ${pool_id}    ${INVITED_STUDENT_EMAIL}
    Run Keyword And Ignore Error    Delete Cognito User Pool Best Effort    ${pool_id}

Get Cognito User Pool Id
    Run Keyword If    '${CREATED_COGNITO_USER_POOL_ID}' != ''    Return From Keyword    ${CREATED_COGNITO_USER_POOL_ID}
    Run Keyword If    '${COGNITO_USER_POOL_ID}' != ''    Return From Keyword    ${COGNITO_USER_POOL_ID}
    # The suite file lives in: services/exam-api/tests/robot/
    # .env.localstack lives in: services/exam-api/.env.localstack
    ${env_path}=    Join Path    ${CURDIR}    ..    ..    .env.localstack
    ${pool}=    Evaluate    (next((line.split("=", 1)[1].strip() for line in open(r"${env_path}", encoding="utf-8") if line.startswith("COGNITO_USER_POOL_ID=")), "") if __import__("os").path.exists(r"${env_path}") else "")
    RETURN    ${pool}

Delete Cognito User Best Effort
    [Arguments]    ${pool_id}    ${username}
    Run Keyword If    '${pool_id}' == ''    Return From Keyword    ${None}
    Run Keyword If    '${username}' == ''    Return From Keyword    ${None}
    # Cognito "Username" is the email used when creating the teacher account.
    Run Cognito Aws Cli Best Effort    cognito-idp admin-delete-user --user-pool-id ${pool_id} --username ${username}

Bootstrap Cognito User Pool If Requested
    Run Keyword If    '${CREATE_COGNITO_USER_POOL}'.lower() != 'true'    Return From Keyword    ${None}
    Run Keyword If    '${COGNITO_USER_POOL_ID}' != ''    Return From Keyword    ${None}

    ${create_pool_result}=    Run Cognito Aws Cli
    ...    cognito-idp create-user-pool --pool-name robot-local-pool --query 'UserPool.Id' --output text
    Should Be Equal As Integers    ${create_pool_result.rc}    0
    ${pool_id}=    Evaluate    $create_pool_result.stdout.strip()
    Set Suite Variable    ${COGNITO_USER_POOL_ID}    ${pool_id}
    Set Suite Variable    ${CREATED_COGNITO_USER_POOL_ID}    ${pool_id}

    ${create_client_result}=    Run Cognito Aws Cli
    ...    cognito-idp create-user-pool-client --user-pool-id ${pool_id} --client-name robot-local-client --explicit-auth-flows ALLOW_USER_PASSWORD_AUTH ALLOW_REFRESH_TOKEN_AUTH --query 'UserPoolClient.ClientId' --output text
    Should Be Equal As Integers    ${create_client_result.rc}    0
    ${client_id}=    Evaluate    $create_client_result.stdout.strip()
    Set Suite Variable    ${COGNITO_APP_CLIENT_ID}    ${client_id}

    Should Not Be Empty    ${ADMIN_EMAIL}
    Should Not Be Empty    ${ADMIN_PASSWORD}
    FOR    ${group_name}    IN    admin    teachers    students
        ${create_group_result}=    Run Cognito Aws Cli
        ...    cognito-idp create-group --user-pool-id ${pool_id} --group-name ${group_name}
        Should Be Equal As Integers    ${create_group_result.rc}    0
    END
    ${create_admin_result}=    Run Cognito Aws Cli
    ...    cognito-idp admin-create-user --user-pool-id ${pool_id} --username ${ADMIN_EMAIL} --user-attributes Name=email,Value=${ADMIN_EMAIL} Name=email_verified,Value=true --message-action SUPPRESS
    Should Be Equal As Integers    ${create_admin_result.rc}    0
    ${set_admin_password_result}=    Run Cognito Aws Cli
    ...    cognito-idp admin-set-user-password --user-pool-id ${pool_id} --username ${ADMIN_EMAIL} --password ${ADMIN_PASSWORD} --permanent
    Should Be Equal As Integers    ${set_admin_password_result.rc}    0
    ${add_admin_group_result}=    Run Cognito Aws Cli
    ...    cognito-idp admin-add-user-to-group --user-pool-id ${pool_id} --username ${ADMIN_EMAIL} --group-name admin
    Should Be Equal As Integers    ${add_admin_group_result.rc}    0

Delete Cognito User Pool Best Effort
    [Arguments]    ${pool_id}
    Run Keyword If    '${DELETE_COGNITO_USER_POOL_ON_TEARDOWN}'.lower() != 'true'    Return From Keyword    ${None}
    Run Keyword If    '${pool_id}' == ''    Return From Keyword    ${None}
    Run Cognito Aws Cli Best Effort    cognito-idp delete-user-pool --user-pool-id ${pool_id}

Run Cognito Aws Cli
    [Arguments]    ${aws_cli_args}
    ${command}=    Catenate    SEPARATOR=
    ...    export AWS_REGION=${AWS_REGION} COGNITO_ENDPOINT_URL=${COGNITO_ENDPOINT_URL}; if [ -n "${AWS_ACCESS_KEY_ID}" ]; then export AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}; fi; if [ -n "${AWS_SECRET_ACCESS_KEY}" ]; then export AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}; fi; if [ -n "${AWS_SESSION_TOKEN}" ]; then export AWS_SESSION_TOKEN=${AWS_SESSION_TOKEN}; fi;
    ...    if [ -n "${COGNITO_ENDPOINT_URL}" ]; then aws --endpoint-url "${COGNITO_ENDPOINT_URL}" ${aws_cli_args}; else aws ${aws_cli_args}; fi
    ${result}=    Run Process    bash    -lc    ${command}
    RETURN    ${result}

Run Cognito Aws Cli Best Effort
    [Arguments]    ${aws_cli_args}
    ${result}=    Run Cognito Aws Cli    ${aws_cli_args}
    RETURN    ${result}
