!C    File: legacy_data.f
!C    Format: F77 Fixed-Form
!C    Purpose: Implement BLOCK DATA for initializing COMMON blocks.
      BLOCK DATA INIT_DAT
      COMMON /SHARED_DAT/ ALPHA, BETA
      REAL ALPHA, BETA
!C    Initialize values for the COMMON block defined in kernel_legacy.f
      DATA ALPHA /1.5/, BETA /2.5/
      END BLOCK DATA INIT_DAT