scenarios: 420   toggle: twins
  OFF 100/420
  OFF 200/420
  OFF 300/420
  OFF 400/420
  OFF done in 376s
  ON  100/420
  ON  200/420
  ON  300/420
  ON  400/420
  ON  done in 533s

planned OFF=85  ON=112
pre-existing PRIMARY designs byte-identical: 85/85   (primary + alternatives: 36/85)
LOST: 0   GAINED: 27   crashes OFF=0 ON=0

   footprint bd/wet/safe   asked   built     %  validators  strategy
20.0x10.0     2/3/Y         200.0   159.0   80%  pass       FRONT_PUBLIC_BAND (twin)   <-- not counted
18.0x12.0     2/1/Y         216.0   141.6   66%  pass       SPINE_PUBLIC_PRIVATE (twin)   <-- not counted
12.0x18.0     2/2/N         216.0    99.4   46%  pass       SPINE_PUBLIC_PRIVATE (twin)   <-- not counted
24.0x13.0     2/1/Y         312.0   185.9   60%  pass       SPINE_PUBLIC_PRIVATE (twin)   <-- not counted
24.0x13.0     2/2/Y         312.0   206.7   66%  pass       SPINE_PUBLIC_PRIVATE (twin)   <-- not counted
18.0x20.0     2/2/Y         360.0   214.7   60%  pass       SPINE_PUBLIC_PRIVATE (twin)   <-- not counted
20.0x22.0     2/3/Y         440.0   232.9   53%  pass       SPINE_PUBLIC_PRIVATE (twin)   <-- not counted
10.0x20.0     3/1/Y         200.0   187.5   94%  pass       FRONT_PUBLIC_BAND (twin)
12.0x18.0     3/1/Y         216.0   189.0   88%  pass       FRONT_PUBLIC_BAND (twin)
14.0x16.0     3/2/N         224.0   185.6   83%  pass       SPINE_PUBLIC_PRIVATE (twin)
18.0x20.0     3/1/N         360.0   206.9   57%  pass       SPINE_PUBLIC_PRIVATE (twin)   <-- not counted
11.0x12.0     4/1/Y         132.0   132.0  100%  pass       FRONT_PUBLIC_BAND (twin)
14.0x14.29    4/2/Y         200.0   198.1   99%  pass       SPINE_DOUBLE_LOADED (twin)
10.0x20.0     4/1/Y         200.0   200.0  100%  pass       FRONT_PUBLIC_BAND (twin)
14.0x16.0     4/1/Y         224.0   139.6   62%  pass       SPINE_SERVICE_CLUSTER (twin)   <-- not counted
12.5x14.5     5/2/Y         181.2   179.8   99%  pass       FRONT_PUBLIC_BAND (twin)
12.5x14.5     5/3/Y         181.2   179.8   99%  pass       FRONT_PUBLIC_BAND (twin)
12.5x14.5     5/1/Y         181.2   181.2  100%  pass       FRONT_PUBLIC_BAND (twin)
12.5x14.5     5/3/Y         181.2   179.8   99%  pass       FRONT_PUBLIC_BAND (twin)
18.0x12.0     5/1/Y         216.0   186.0   86%  pass       FRONT_PUBLIC_BAND (twin)
18.0x12.0     5/2/Y         216.0   190.8   88%  pass       FRONT_PUBLIC_BAND (twin)
18.0x12.0     5/1/Y         216.0   186.0   86%  pass       FRONT_PUBLIC_BAND (twin)
18.0x12.0     5/2/Y         216.0   190.8   88%  pass       FRONT_PUBLIC_BAND (twin)
12.0x18.0     5/1/Y         216.0   212.4   98%  pass       FRONT_PUBLIC_BAND (twin)
12.5x14.5     6/2/Y         181.2   179.8   99%  pass       FRONT_PUBLIC_BAND (twin)
12.5x14.5     6/2/Y         181.2   179.8   99%  pass       FRONT_PUBLIC_BAND (twin)
12.0x18.0     6/1/Y         216.0   216.0  100%  pass       FRONT_PUBLIC_BAND (twin)
counted as gains (>=80% of ask, validators pass): 18/27

refusal codes:
  PLAN_FAILED_VALIDATION                               OFF=   2  ON=  15
  PLAN_NOT_REALIZABLE                                  OFF=  47  ON=  26
  PLAN_NOT_REALIZABLE+outline                          OFF=  89  ON=  87
  TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY         OFF= 197  ON= 180

strategy of delivered plans (ON): {'SPINE_PUBLIC_PRIVATE': 47, 'FRONT_PUBLIC_BAND': 24, 'SPINE_SERVICE_CLUSTER': 24, 'SPINE_DOUBLE_LOADED': 17}
latency already planned (n=85): median OFF 0.83s -> ON 1.14s   worst regression +0.70s
latency not planned before (n=335): median OFF 0.52s -> ON 0.61s   worst regression +6.42s
total OFF 376s   ON 533s
