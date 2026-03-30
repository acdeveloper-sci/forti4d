MODULE model_types
  ! Scope E4: Explicit IMPLICIT NONE in module
  IMPLICIT NONE
  
  ! Scope E4: Derived TYPE with components
  TYPE :: node_data
     REAL :: temperature
     REAL :: stress_tensor_xx
     INTEGER :: material_id
  END TYPE node_data

! Structure: INTERFACE block detection for inventario.py
  INTERFACE
     SUBROUTINE external_logger(msg_id, status)
        INTEGER, INTENT(IN) :: msg_id, status
     END SUBROUTINE external_logger
  END INTERFACE

END MODULE model_types

PROGRAM solver_main
  USE model_types  ! Dependencies: USE module
  IMPLICIT NONE

  ! Scope E4: F90 Declarations
  INTEGER :: nx, ny, alloc_stat, i, j, status_flag
  LOGICAL :: grid_ok

  ! E4 Scope/Linting: Declared but UNUSED derived type variable
  TYPE(node_data) :: sensor_pt
  
  ! Static array declaration (fixed size)
  REAL, DIMENSION(3, 3) :: stress_matrix
  
  ! Dynamic memory F90: ALLOCATABLE array declaration
  REAL, DIMENSION(:,:), ALLOCATABLE :: grid

  ! Simulate dynamic sizing
  nx = 10
  ny = 10 

  ! Initialize static array
  stress_matrix(1,1) = 0.0

  ! Dynamic memory F90: ALLOCATE statement with STAT
  ALLOCATE(grid(nx, ny), STAT=alloc_stat)
  IF (alloc_stat /= 0) THEN
     PRINT *, "Error: Memory allocation failed for grid"
     STOP
  END IF

  ! Complexity: FORALL and WHERE
  FORALL (i = 1:nx, j = 1:ny)
     grid(i,j) = 0.0
  END FORALL

  WHERE (grid < 1.0) grid = 1.0

  status_flag = 2
  
  ! Complexity: SELECT CASE with multiple CASEs and CASE DEFAULT
  SELECT CASE (status_flag)
     CASE (1)
        PRINT *, "Starting mesh analysis"
     CASE (2)
        PRINT *, "Starting transient simulation"
     CASE DEFAULT
        PRINT *, "Unknown mode"
  END SELECT

  ! Dependencies: CALL between units

  ! Reachability: Unit reachable from PROGRAM (CC Medium ~6)
  CALL validate_grid(grid, nx, ny, grid_ok)
  
  ! Reachability: Unit reachable from PROGRAM
  IF (grid_ok) THEN
     CALL compute_step(grid, nx, ny)
  END IF

  ! Dependencies: Function call as expression (FUNC_CALL)
  IF (check_convergence(grid) > 0.99) THEN
     PRINT *, "Convergence reached"
  END IF

  ! Dependencies: Implicit orphan subroutine call
  ! SLOC: F90 continuation line using '&'
  CALL export_vtk_mesh(grid, &
                       nx, ny)

  ! Dynamic memory F90: DEALLOCATE and ALLOCATED intrinsic
  IF (ALLOCATED(grid)) THEN
     DEALLOCATE(grid)
     PRINT *, "Memory successfully deallocated"
  END IF

CONTAINS ! Structure: Nested units

! Complexity: Medium CC (~6) for the medium tier coverage
  SUBROUTINE validate_grid(data_grid, x_dim, y_dim, is_valid)
     INTEGER, INTENT(IN) :: x_dim, y_dim
     REAL, DIMENSION(x_dim, y_dim), INTENT(IN) :: data_grid
     LOGICAL, INTENT(OUT) :: is_valid
     INTEGER :: row, col, error_count

     ! Base CC = 1
     is_valid = .TRUE.
     error_count = 0

     ! 1. DO loop (+1 CC -> 2)
     DO row = 1, x_dim
        ! 2. DO loop (+1 CC -> 3)
        DO col = 1, y_dim
           ! 3. IF statement (+1 CC -> 4)
           ! 4. Logical OR (+1 CC -> 5) [depending on complexity.py rules]
           IF (data_grid(row,col) < 0.0 .OR. data_grid(row,col) > 1000.0) THEN
              error_count = error_count + 1
           ! 5. ELSE IF statement (+1 CC -> 6)
           ELSE IF (data_grid(row,col) == 0.0) THEN
              CONTINUE ! Warning placeholder
           END IF
        END DO
     END DO

     ! 6. IF statement (+1 CC -> 7)
     IF (error_count > 0) THEN
        is_valid = .FALSE.
     END IF
  END SUBROUTINE validate_grid

  SUBROUTINE compute_step(data_grid, x_dim, y_dim)
     ! Removed INTENT to reflect typical transitional F90 code
     INTEGER :: x_dim, y_dim
     REAL, DIMENSION(x_dim, y_dim) :: data_grid
     data_grid(1,1) = data_grid(1,1) * 1.05
  END SUBROUTINE compute_step

  FUNCTION check_convergence(data_grid) RESULT(val)
     ! Kept INTENT here solely to satisfy the parser test requirement
     REAL, DIMENSION(:,:), INTENT(IN) :: data_grid
     REAL :: val
     ! Complexity: Purely sequential unit (CC=1)
     ! Now using the dummy argument to compute a result
     val = MAXVAL(data_grid) / 100.0
  END FUNCTION check_convergence

END PROGRAM solver_main