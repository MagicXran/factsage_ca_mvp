REM ===== run_equilib.mac (FactSage 8.3/8.4) =====
VARIABLE %EquiFile %OutDir %TempC %PressAtm
HIDE
HIDE_MACRO

%EquiFile = "{{EQUI_FILE}}"
%OutDir   = "{{OUT_DIR}}"

%TempC    = {{TEMP_C}}
%PressAtm = {{PRESS_ATM}}

OPEN %EquiFile
SET FINAL T %TempC
SET FINAL P %PressAtm

CALC

SAVE "%OutDirresult.xml"
SAVE "%OutDirresult.res"

END
