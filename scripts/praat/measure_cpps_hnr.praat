form Measure CPPS and HNR
    sentence file
endform

sound = Read from file: file$
cepstrogram = To PowerCepstrogram: 60, 0.002, 5000, 50
cpps = Get CPPS: "no", 0.01, 0.001, 60, 330, 0.05, "parabolic", 0.001, 0.0, "Straight", "Robust"

selectObject: sound
harmonicity = To Harmonicity (cc): 0.01, 75.0, 0.1, 1.0
hnr = Get mean: 0, 0

selectObject: sound
formant = To Formant (burg): 0.0, 5.0, 5500.0, 0.025, 50.0
selectObject: formant
f1 = Get mean: 1, 0, 0, "Hertz"
f2 = Get mean: 2, 0, 0, "Hertz"
f3 = Get mean: 3, 0, 0, "Hertz"

writeInfoLine: "CPPS=", cpps, tab$, "HNR=", hnr, tab$, "F1=", f1, tab$, "F2=", f2, tab$, "F3=", f3
