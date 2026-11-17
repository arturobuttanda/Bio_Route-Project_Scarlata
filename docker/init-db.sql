-- Inicialización de extensiones geoespaciales y schema principal
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
-- Nota: pgrouting puede activarse si la imagen base lo soporta
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS pgrouting;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'pgrouting extension not available in base image, continuing with PostGIS core';
END $$;

-- Schema para datos analíticos de movilidad
CREATE SCHEMA IF NOT EXISTS geodata;

-- Confirmación de extensiones en log
SELECT PostGIS_Full_Version();
