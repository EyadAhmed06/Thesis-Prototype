"""Rebuild everything SUMO needs, from the two public downloads.
  1. Michigan OpenStreetMap extract (michigan-latest.osm.pbf, e.g. from download.geofabrik.de/north-america/us/michigan.html)
  2. AFDC station list for Michigan, electric only, as CSV (afdc.energy.gov/stations -> download)
Needs: pip install eclipse-sumo osmium pandas numpy scipy
Usage: python build_network.py michigan-latest.osm.pbf afdc_michigan.csv
Writes data/aa_det.osm, data/aa_det.net.xml (about 180 MB) and referee/chargers.csv."""
import os, sys, subprocess
here = os.path.dirname(os.path.abspath(__file__)); data = os.path.join(here, 'data'); os.makedirs(data, exist_ok=True)
pbf, afdc = sys.argv[1], sys.argv[2]
osm, net = os.path.join(data, 'aa_det.osm'), os.path.join(data, 'aa_det.net.xml')
home = os.environ.get('SUMO_HOME') or __import__('sumo').SUMO_HOME
# step 1 (Python): keep main roads inside the Ann Arbor-Detroit box
subprocess.run([sys.executable, os.path.join(here, 'sim-validation', 'mi_osm.py'), pbf, osm], check=True)
# step 2 (SUMO's own converter): OpenStreetMap XML -> SUMO network XML
subprocess.run([os.path.join(home, 'bin', 'netconvert'), '--osm-files', osm, '-o', net,
                '--geometry.remove', '--ramps.guess', '--junctions.join', '--tls.guess-signals',
                '--keep-edges.components', '1', '--remove-edges.isolated'], check=True)
# step 3 (Python): snap every charger to the network
subprocess.run([sys.executable, os.path.join(here, 'referee', 'stations.py'), afdc, net, os.path.join(here, 'referee', 'chargers.csv')], check=True)
print('done:', net)
