import pyorthanc
from headers.header_pet import exportar_series_pet
from headers.header_ct import exportar_series_ct
from config import ORTHANC_URL, ORTHANC_USER, ORTHANC_PASS

# Conectar a Orthanc
client = pyorthanc.Orthanc(ORTHANC_URL, ORTHANC_USER, ORTHANC_PASS, timeout = 60, trust_env = False)

# Ejecutar exportación de series CT
def main():
    exportar_series_ct(client, output_dir="header_ct")
    exportar_series_pet(client, output_dir="header_pet")


if __name__ == "__main__":
    main()