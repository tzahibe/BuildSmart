from topo_lib import *
# K4: not rectangular; one L room fixes it
K4n = ["a","b","c","d"]; K4e = [("a","b"),("a","c"),("a","d"),("b","c"),("b","d"),("c","d")]
print("K4 rect:", solve_family(K4n,K4e,"rect")[0], "| K4 with L(a):", solve_family(K4n,K4e,"rect",l_rooms=("a",))[0])
# pinwheel C5 = center + 4 arms cycle: non-slicing but rectangular
Pn=["c","n","e","s","w"]; Pe=[("c","n"),("c","e"),("c","s"),("c","w"),("n","e"),("e","s"),("s","w"),("w","n")]
print("pinwheel band:", solve_family(Pn,Pe,"band_y")[0], "slicing:", solve_family(Pn,Pe,"slicing")[0], "rect:", solve_family(Pn,Pe,"rect")[0])
# triple lens: edge a-b with 3 common nbrs
Tn=["a","b","x","y","z"]; Te=[("a","b"),("a","x"),("b","x"),("a","y"),("b","y"),("a","z"),("b","z")]
print("lens3 rect:", solve_family(Tn,Te,"rect")[0], "| with L(a):", solve_family(Tn,Te,"rect",l_rooms=("a",))[0])
# star K1,8 (hub) : band? yes with hub full-width band
Sn=["h"]+[f"r{i}" for i in range(8)]; Se=[("h",r) for r in Sn[1:]]
print("star K1,8 band:", solve_family(Sn,Se,"band_y")[0])
# 2x2 grid cycle C4 band yes; C4 plus chord = ok
print("C4 band:", solve_family(["a","b","c","d"],[("a","b"),("b","c"),("c","d"),("d","a")],"band_y")[0])
# K2,3 (not band? a,b both adjacent to x,y,z): 
print("K2,3 band:", solve_family(["a","b","x","y","z"],[("a","x"),("a","y"),("a","z"),("b","x"),("b","y"),("b","z")],"band_y")[0],
      "slicing:", solve_family(["a","b","x","y","z"],[("a","x"),("a","y"),("a","z"),("b","x"),("b","y"),("b","z")],"slicing")[0])
