form Measure calibrated CPPS and HNR time series
    sentence file
    sentence output
endform

sound = Read from file: file$
cepstrogram = To PowerCepstrogram: 60, 0.002, 5000, 50
cppsMean = Get CPPS: "no", 0.01, 0.001, 60, 330, 0.05, "parabolic", 0.001, 0.0, "Straight", "Robust"

selectObject: cepstrogram
smoothed = Smooth: 0.01, 0.001
cppTable = To Table (cepstral peak prominences): "yes", "yes", 6, 6, "no", 3, 60, 330, 0.05, "parabolic", 0.001, 0.0, "Straight", "Robust"

selectObject: sound
harmonicity = To Harmonicity (cc): 0.01, 75.0, 0.1, 1.0

writeFileLine: output$, "time_s", tab$, "praat_cpps_db", tab$, "praat_hnr_cc_db"
selectObject: cppTable
n = Get number of rows
for i from 1 to n
    time = Get value: i, "time(s)"
    cpp = Get value: i, "CPP(dB)"
    selectObject: harmonicity
    hnr = Get value at time: time, "cubic"
    if hnr = undefined
        appendFileLine: output$, fixed$ (time, 6), tab$, fixed$ (cpp, 6), tab$, ""
    else
        appendFileLine: output$, fixed$ (time, 6), tab$, fixed$ (cpp, 6), tab$, fixed$ (hnr, 6)
    endif
    selectObject: cppTable
endfor

writeInfoLine: "CPPS_MEAN=", cppsMean, tab$, "ROWS=", n
