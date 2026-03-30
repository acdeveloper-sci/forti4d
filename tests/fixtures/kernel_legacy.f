C     File: kernel_legacy.f
C     Format: F77 Fixed-Form
C     Purpose: Numerical routine with legacy constructs
      SUBROUTINE LEGACY_CALC(X, Y, RES)
C     Scope E4: IMPLICIT with rules
      IMPLICIT REAL (A-H, O-Z)
      IMPLICIT INTEGER (I-N)

C     Scope E4: F77 Declarations
      DIMENSION X(10), Y(10)
      REAL RES
      REAL A, B, C
      INTEGER FLAG

C     Legacy constructs: COMMON block (shared)
      COMMON /SHARED_DAT/ ALPHA, BETA

C     Scope E4: Simple and transitive EQUIVALENCE (A<->B, B<->C)
      EQUIVALENCE (A, B)
      EQUIVALENCE (B, C)

C     Dependencies: Reference to explicitly declared external symbol
      EXTERNAL TIMER_C

      A = 10.0
      FLAG = -1

C     Legacy constructs: Arithmetic IF
      IF (FLAG) 10, 20, 30

 10   CONTINUE
C     SLOC: F77 continuation line (character in column 6)
      RES = X(1) + Y(1) + 
     +      ALPHA
      GOTO 40

 20   CONTINUE
      RES = 0.0
      GOTO 40

 30   CONTINUE
      RES = X(1) * Y(1) * BETA

 40   CONTINUE
      CALL TIMER_C()

C     Legacy constructs: PAUSE
      PAUSE 'Legacy calc paused for review'

      RETURN

C     Legacy constructs: ENTRY
      ENTRY ALT_CALC(X, RES)
      RES = X(1) * 2.0
      RETURN
      END