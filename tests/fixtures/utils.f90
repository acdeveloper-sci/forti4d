! File: utils.f90
! Purpose: Base file for clone and ambiguity detection tests.

! Structure: Named (generic) INTERFACE block — GENERIC_INTERFACE unit
INTERFACE math_generic
  SUBROUTINE math_util_a(x, y, res)
    REAL, INTENT(IN) :: x, y
    REAL, INTENT(OUT) :: res
  END SUBROUTINE math_util_a
END INTERFACE math_generic

MODULE utils_mod
  IMPLICIT NONE

CONTAINS

  ! Clone type: IDENTICAL (Target)
  SUBROUTINE math_util_a(x, y, res)
    REAL, INTENT(IN) :: x, y
    REAL, INTENT(OUT) :: res
    res = x + y
  END SUBROUTINE math_util_a

  ! Clone type: SIMILAR (Target)
  FUNCTION math_util_b(x) RESULT(val)
    REAL, INTENT(IN) :: x
    REAL :: val
    val = x * x + 2.0 * x
  END FUNCTION math_util_b

! Clone type: IDENTICAL (Target)
  ! Application: Civil engineering (Structural load)
  SUBROUTINE compute_load(force, area, stress)
    REAL, INTENT(IN) :: force, area
    REAL, INTENT(OUT) :: stress
    stress = force / area
  END SUBROUTINE compute_load

  ! Clone type: SIMILAR (Target)
  ! Application: Other sciences (Biology/Population growth)
  FUNCTION calc_growth(rate) RESULT(val)
    REAL, INTENT(IN) :: rate
    REAL :: val
    val = rate * rate + 2.0 * rate
  END FUNCTION calc_growth

  ! Clone type: DIVERGENT / AMBIGUITY (Target)
  ! Application: General math
  SUBROUTINE calc_metrics(data_array, n, res)
    INTEGER, INTENT(IN) :: n
    REAL, DIMENSION(n), INTENT(IN) :: data_array
    REAL, INTENT(OUT) :: res
    ! Original logic: computes the sum of the array
    res = SUM(data_array)
  END SUBROUTINE calc_metrics

END MODULE utils_mod