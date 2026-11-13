#include "dp/model.hpp"
#include <boost/version.hpp>
#include <fstream>
#include <iostream>
#include <string>

int main(int argc, char **argv) {
  try {
    dp::Config config;
    bool tracing = false;
    for (int argument_index = 1; argument_index < argc; ++argument_index) {
      const std::string arg = argv[argument_index];
      if (arg == "--trace")
        tracing = true;
      else if (arg == "--config" && argument_index + 1 < argc) {
        std::ifstream config_stream(argv[++argument_index]);
        if (!config_stream)
          throw std::invalid_argument("cannot read config");
        dp::Json json_value;
        config_stream >> json_value;
        config = dp::config_from_json(json_value);
      } else if (arg == "--version") {
        std::cout << dp::Json({{"model", "dp-cmodel-2"},
                               {"architecture", "dp_top/v1.8; other frontends/v1.7"},
                               {"frontends", dp::Json::array({"multi", "e", "qe", "t8h16q32e96", "t8h16q32e128", "t8h16q32e192", "t8h16q32e256", "t8h16q64e128", "q", "t8h16q64e64", "t8h16q96e192", "t8h16q128e256"})},
                               {"boost", BOOST_LIB_VERSION},
                               {"json", NLOHMANN_JSON_VERSION_MAJOR * 10000 +
                                            NLOHMANN_JSON_VERSION_MINOR * 100 +
                                            NLOHMANN_JSON_VERSION_PATCH}})
                         .dump()
                  << '\n';
        return 0;
      } else
        throw std::invalid_argument("usage: dp_cmodel_cli [--config FILE] [--trace] [--version]");
    }
    dp::Pipeline pipeline(config, tracing);
    std::string line;
    bool failed = false;
    while (std::getline(std::cin, line)) {
      if (line.empty())
        continue;
      try {
        const auto json_value = dp::Json::parse(line);
        const std::string op = json_value.value("op", std::string("eval"));
        dp::Json output;
        if (op == "config")
          output = dp::config_json(config);
        else if (op == "eval")
          output = dp::result_json(
              dp::evaluate(config, dp::request_from_json(json_value.at("request")), tracing));
        else if (op == "step") {
          std::optional<dp::Request> request;
          const bool reset_requested = json_value.value("reset", false);
          const bool a_valid = json_value.value("a_valid", false);
          const bool b_valid = json_value.value("b_valid", false);
          const bool c_valid = json_value.value("c_valid", false);
          if (!reset_requested && a_valid && b_valid && c_valid && json_value.contains("request"))
            request = dp::request_from_json(json_value.at("request"));
          output =
              dp::tick_json(pipeline.step(request, a_valid, b_valid, c_valid, reset_requested));
        } else
          throw std::invalid_argument("unknown operation");
        std::cout << output.dump() << '\n';
      } catch (const std::exception &error) {
        failed = true;
        std::cout << dp::Json({{"error", error.what()}}).dump() << '\n';
      }
    }
    return failed ? 2 : 0;
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 2;
  }
}
