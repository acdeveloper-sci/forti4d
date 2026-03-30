! File: mesh_hybrid.f90
! Format: Free-form (F90) but heavily procedural F77 style logic.
! Purpose: Test high Cyclomatic Complexity (CC > 10).
! Application: Geophysics or civil engineering (Mesh processing)
SUBROUTINE process_mesh(nodes, n_elements, threshold)
  IMPLICIT NONE
  INTEGER, INTENT(IN) :: n_elements
  REAL, DIMENSION(n_elements), INTENT(INOUT) :: nodes
  REAL, INTENT(IN) :: threshold
  
  INTEGER :: i, j, k, status_flag
  REAL :: temp_val

  ! Base path (CC = 1)
  i = 1
  
  ! 1. DO WHILE loop (+1 CC -> 2)
  DO WHILE (i <= n_elements)
     temp_val = nodes(i)
     
     ! 2. IF statement (+1 CC -> 3)
     IF (temp_val > threshold) THEN
        status_flag = 1
     ! 3. ELSE IF statement (+1 CC -> 4)
     ELSE IF (temp_val > threshold * 0.5) THEN
        status_flag = 2
     ! 4. ELSE IF statement (+1 CC -> 5)
     ELSE IF (temp_val < 0.0) THEN
        status_flag = 3
     ELSE
        status_flag = 0
     END IF
     
     ! 5. SELECT CASE branch 1 (+1 CC -> 6)
     ! 6. SELECT CASE branch 2 (+1 CC -> 7)
     ! 7. SELECT CASE branch 3 (+1 CC -> 8)
     SELECT CASE (status_flag)
        CASE (1)
           nodes(i) = threshold
        CASE (2)
           nodes(i) = temp_val * 1.1
        CASE (3)
           nodes(i) = 0.0
        CASE DEFAULT
           nodes(i) = temp_val
     END SELECT
     
     ! 8. DO loop (+1 CC -> 9)
     DO j = 1, 5
        ! 9. IF statement (+1 CC -> 10)
        IF (j == 3) THEN
           ! 10. DO loop (+1 CC -> 11)
           DO k = 1, 2
              ! 11. IF statement (+1 CC -> 12)
              IF (nodes(i) < 0.0) nodes(i) = 0.0
           END DO
        END IF
     END DO
     
     i = i + 1
  END DO
  ! Final Cyclomatic Complexity = 12 (> 10)
END SUBROUTINE process_mesh