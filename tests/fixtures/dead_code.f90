! File: dead_code.f90
! Purpose: Test dead code detection and shared subroutines across executables.
PROGRAM dead_test
  IMPLICIT NONE
  REAL :: test_val
  
  ! Scope E4: Standalone PARAMETER
  REAL, PARAMETER :: PI = 3.14159265
  
  test_val = PI
  CALL SHARED_ROUTINE(test_val)
  
  STOP 'Program execution halted normally'
  
  ! Reachability: DEAD CODE (unreachable after STOP)
  test_val = 0.0
  PRINT *, "This line is dead code and should never execute."
  
END PROGRAM dead_test

! Reachability: Shared subroutine called by dead_code.f90 and implicit_run.f
SUBROUTINE SHARED_ROUTINE(V)
  REAL, INTENT(IN) :: V
  PRINT *, 'Shared routine executed with value: ', V
END SUBROUTINE SHARED_ROUTINE

! Reachability: GHOST UNIT (Subroutine never called anywhere in the corpus)
SUBROUTINE GHOST_ROUTINE()
  PRINT *, "I am an orphaned subroutine. CC=1, but reachability is 0."
END SUBROUTINE GHOST_ROUTINE