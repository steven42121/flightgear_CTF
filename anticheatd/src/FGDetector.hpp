#pragma once
/**
 * FlightGear installation auto-detection.
 *
 * Priority on Windows:
 *   1. %FG_ROOT% environment variable
 *   2. Registry: HKLM\SOFTWARE\FlightGear\InstallLocation
 *   3. Common paths: C:\Program Files\FlightGear*
 *   4. PATH search for fgfs.exe
 *
 * Priority on Linux:
 *   1. $FG_ROOT environment variable
 *   2. Common paths: /usr/share/games/flightgear, /usr/share/flightgear
 *   3. which fgfs
 *
 * Returns empty string if not found.
 */
#include <string>

namespace fg_detect {

struct FGLocations {
    std::string data_root;    // FGData directory (FG_ROOT)
    std::string bin_dir;      // Directory containing fgfs[.exe]
    std::string scenery_dir;  // TerraSync or standalone scenery

    bool valid() const { return !data_root.empty() && !bin_dir.empty(); }
};

FGLocations detect();

} // namespace fg_detect