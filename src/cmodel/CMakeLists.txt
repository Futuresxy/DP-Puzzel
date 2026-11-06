cmake_minimum_required(VERSION 3.16)
project(dp_cmodel VERSION 1.0 LANGUAGES CXX)
find_package(Boost 1.83.0 EXACT REQUIRED)
find_package(nlohmann_json 3.11.3 EXACT REQUIRED)
add_library(dp_cmodel
  lib/config.cpp lib/arithmetic.cpp lib/unpack.cpp lib/lane.cpp
  lib/group.cpp lib/lane/lane_e.cpp lib/group/group_e.cpp lib/top/backend.cpp
  lib/model.cpp lib/json_io.cpp)
target_include_directories(dp_cmodel PUBLIC include PRIVATE lib)
target_link_libraries(dp_cmodel PUBLIC Boost::boost nlohmann_json::nlohmann_json)
target_compile_features(dp_cmodel PUBLIC cxx_std_17)
target_compile_options(dp_cmodel PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_executable(dp_cmodel_cli main.cpp)
target_link_libraries(dp_cmodel_cli PRIVATE dp_cmodel)
option(DP_SANITIZE "Enable address and undefined-behavior checks" OFF)
if(DP_SANITIZE)
  target_compile_options(dp_cmodel PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer)
  target_link_options(dp_cmodel PUBLIC -fsanitize=address,undefined)
endif()
