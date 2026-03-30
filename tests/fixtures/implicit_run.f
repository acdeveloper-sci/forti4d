C     File: implicit_run.f
C     Format: F77 Fixed-Form
C     Purpose: IMPLICIT-MAIN (no PROGRAM statement), INCLUDE directive.
C     Application: Hydrology (Runoff calculation script)
      IMPLICIT NONE
      REAL VAL
      
C     Dependency: INCLUDE directive
      INCLUDE 'params.inc'
      
      VAL = 10.0
C     Dependency: Call to a subroutine shared between two programs
      CALL SHARED_ROUTINE(VAL)
      
      PRINT *, 'Max iterations: ', MAX_ITER
      END