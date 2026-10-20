# Test Case Sheet: Delivery Operations Platform (Phase 1)

Priority: P1 = must pass, P2 = important, P3 = nice to have.
Type: P = positive, N = negative, B = boundary, S = security.
Status values are filled only after the case was really executed.

| ID | Area | Type | Priority | Scenario | Steps | Expected result | Covered by | Status |
|---|---|---|---|---|---|---|---|---|
| TC-001 | Health | P | P2 | API is alive | GET /health | 200 and a healthy response | tests/test_health.py | Pass |
| TC-002 | Shipment | P | P1 | Create a valid shipment | POST /shipments with valid name, phone, address, zone | 201, status = created | tests/test_shipments_api.py | Pass |
| TC-003 | Shipment | N | P1 | Invalid phone number | POST /shipments with phone not matching 01 + 9 digits | 422 validation error | tests/test_shipments_api.py | Pass |
| TC-004 | Shipment | N | P2 | COD shipment without amount | POST /shipments with is_cod = true and amount 0 | 422 validation error | tests/test_shipments_api.py | Pass |
| TC-005 | State machine | P | P1 | Legal transition | Change status created -> assigned with a rider of the same zone | 200, status = assigned | tests/test_shipments_api.py | Pass |
| TC-006 | State machine | N | P1 | Illegal transition | Change status created -> delivered | 409 conflict, status unchanged | tests/test_shipments_api.py, tests/test_state_machine.py | Pass |
| TC-007 | Audit | P | P1 | Status change is logged | Change a status, then read audit_log | One row with old, new, actor, time | tests/test_shipments_api.py (test_happy_path_and_audit_trail), tests/test_rbac.py (test_audit_log_records_who_did_it) | Pass |
| TC-008 | Audit | S | P1 | Audit log cannot be changed | Try UPDATE, DELETE, TRUNCATE on audit_log | Database rejects all three | tests/test_audit_log.py | Pass |
| TC-009 | Rules | P | P1 | Phone off -> reschedule | Rider reports attempt_failed, reason phone_off | Status becomes rescheduled, sms_reminder task created | tests/test_exception_flow.py | Pass |
| TC-010 | Rules | B | P1 | Max attempts reached | Third failed attempt on a COD shipment | return_to_sender, block_cod recorded in audit details | tests/test_exception_flow.py | Pass |
| TC-011 | Rules | P | P2 | Wrong address waits for a human | Report attempt_failed, reason wrong_address | Stays attempt_failed, customer_service_task created | tests/test_exception_flow.py, tests/test_rules.py | Pass |
| TC-012 | Auth | N | P1 | Wrong password | POST /login with wrong password | 401, same message as unknown user | tests/test_auth.py | Pass |
| TC-013 | Auth | S | P1 | Forged or expired token | Call a protected endpoint with a forged / expired / alg=none token | 401 | tests/test_auth.py, tests/test_rbac.py | Pass |
| TC-014 | RBAC | S | P1 | Wrong role | Viewer tries to change a status | 403 | tests/test_rbac.py | Pass |
| TC-015 | RBAC | S | P1 | Other rider's data | Rider A requests rider B's shipment | 404 (existence not leaked) | tests/test_rbac.py | Pass |
