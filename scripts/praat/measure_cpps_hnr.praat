form Measure CPPS and HNR
    sentence file
endform

sound = Read from file: file$
cepstrogram = To PowerCepstrogram: 60, 0.002, 5000, 50
cpps = Get CPPS: "no", 0.01, 0.001, 60, 330, 0.05, "parabolic", 0.001, 0.0, "Straight", "Robust"

selectObject: sound
harmonicity = To Harmonicity (cc): 0.01, 75.0, 0.1, 1.0
hnr = Get mean: 0, 0

writeInfoLine: "CPPS=", cpps, tab$, "HNR=", hnr
