cmake_minimum_required(VERSION 3.16)
project(anticheatd VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Output directory
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

# ─── VMAware (header-only, MIT licensed) ───
if(NOT DEFINED VMAWARE_PATH)
    set(VMAWARE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/src")
endif()

# ─── Platform-specific setup ───
if(WIN32)
    # Windows: use BCrypt for crypto (no external OpenSSL needed)
    set(CRYPTO_LIBS bcrypt advapi32)
elseif(APPLE)
    find_library(CORE_FOUNDATION CoreFoundation)
    set(CRYPTO_LIBS ${CORE_FOUNDATION})
elseif(UNIX)
    find_package(OpenSSL REQUIRED)
    find_package(ZLIB REQUIRED)
    set(CRYPTO_LIBS OpenSSL::SSL OpenSSL::Crypto ZLIB::ZLIB dl pthread)
endif()

# ─── Source files ───
set(SOURCES
    src/main.cpp
    src/AntiCheatDaemon.cpp
    src/L0_ArgValidation.cpp
    src/L1_Integrity.cpp
    src/L2_PropertyAudit.cpp
    src/L3_FDMSourceTracker.cpp
    src/L4_ProcessIntegrity.cpp
    src/L5_Heartbeat.cpp
    src/VMDetector.cpp
    src/SessionManager.cpp
    src/Logger.cpp
    src/Config.cpp
    src/hb_secret.cpp
    src/anti_debug.cpp
    src/FGDetector.cpp
)

set(HEADERS
    src/AntiCheatDaemon.hpp
    src/L0_ArgValidation.hpp
    src/L1_Integrity.hpp
    src/L2_PropertyAudit.hpp
    src/L3_FDMSourceTracker.hpp
    src/L4_ProcessIntegrity.hpp
    src/L5_Heartbeat.hpp
    src/VMDetector.hpp
    src/SessionManager.hpp
    src/Logger.hpp
    src/Config.hpp
    src/common.hpp
    src/FGDetector.hpp
    ${VMAWARE_PATH}/vmaware.hpp
)

# ─── Executable ───
add_executable(anticheatd ${SOURCES} ${HEADERS})

target_include_directories(anticheatd PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${VMAWARE_PATH}
)

target_link_libraries(anticheatd PRIVATE ${CRYPTO_LIBS})

# Platform-specific flags
if(WIN32)
    target_compile_definitions(anticheatd PRIVATE _WIN32_WINNT=0x0A00)
    target_compile_options(anticheatd PRIVATE /W4 /WX /utf-8)
    
    # ─── Obfuscation compiler flags ───
    target_compile_options(anticheatd PRIVATE
        /O2           # Max optimization (defeats simple decompilation)
        /Ob2          # Aggressive inlining
        /Oi           # Intrinsic functions
        /GS-          # Disable buffer security check (reduces CRTsig)
        /Gy           # Function-level linking
        /GL           # Whole program optimization
    )
    
    # ─── Obfuscation linker flags ───
    target_link_options(anticheatd PRIVATE
        /LTCG         # Link-time code generation
        /OPT:REF      # Remove unreferenced code
        /OPT:ICF      # Fold identical COMDATs
        /DEBUG:NONE   # No PDB in Release
        /PDBSTRIPPED:NONE
    )
elseif(UNIX)
    target_compile_options(anticheatd PRIVATE -Wall -Wextra -Wpedantic
        -O2 -fomit-frame-pointer -fno-asynchronous-unwind-tables
        -Wl,--strip-all -Wl,--gc-sections
    )
endif()

# ─── Install ───
install(TARGETS anticheatd DESTINATION bin)