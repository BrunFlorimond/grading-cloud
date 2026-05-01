"""Tests for centralised RBAC FastAPI dependency guards (issue #12).

Test cases to implement:
    require_teacher
        - returns CurrentTeacher when JWT has custom:role=teacher
        - raises 401 when Authorization header is absent
        - raises 401 when Authorization scheme is not Bearer
        - raises 401 when JWT signature is invalid
        - raises 403 when JWT custom:role is "student"
        - raises 403 when JWT custom:role is missing

    require_student
        - returns CurrentStudent when JWT has custom:role=student
        - raises 401 when Authorization header is absent
        - raises 401 when Authorization scheme is not Bearer
        - raises 401 when JWT signature is invalid
        - raises 403 when JWT custom:role is "teacher"
        - raises 403 when JWT custom:role is missing

    require_own_data
        - passes when current_student.student_id matches path param
        - raises 403 when current_student.student_id differs from path param

    error body shape
        - 401 responses contain JSON body {"error": str, "code": str}
        - 403 responses contain JSON body {"error": str, "code": str}

    verify_exam_ownership use case
        - calls ExamOwnershipPort.teacher_owns_exam with correct args
        - raises ExamOwnershipError when teacher_owns_exam returns False
        - passes through when teacher_owns_exam returns True

    DynamoDbExamOwnershipRepository
        - returns True when GetItem finds PK=TEACHER#{t} SK=EXAM#{e}
        - returns False when GetItem returns no item
"""
