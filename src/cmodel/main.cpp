#include "dp/model.hpp"
#include <boost/version.hpp>
#include <fstream>
#include <iostream>
#include <string>

int main(int argc,char** argv) {
  try {
    dp::Config config; bool tracing=false;
    for(int i=1;i<argc;++i) {
      const std::string arg=argv[i];
      if(arg=="--trace") tracing=true;
      else if(arg=="--config" && i+1<argc) {
        std::ifstream f(argv[++i]); if(!f) throw std::invalid_argument("cannot read config");
        dp::Json j; f>>j; config=dp::config_from_json(j);
      } else if(arg=="--version") {
        std::cout<<dp::Json({{"model","dp-cmodel-1"},{"architecture","dp-cube/v1.4"},
          {"boost",BOOST_LIB_VERSION},{"json",NLOHMANN_JSON_VERSION_MAJOR*10000+NLOHMANN_JSON_VERSION_MINOR*100+NLOHMANN_JSON_VERSION_PATCH}}).dump()<<'\n'; return 0;
      } else throw std::invalid_argument("usage: dp_cmodel_cli [--config FILE] [--trace] [--version]");
    }
    dp::Pipeline pipeline(config,tracing); std::string line; bool failed=false;
    while(std::getline(std::cin,line)) {
      if(line.empty()) continue;
      try {
        const auto j=dp::Json::parse(line); const std::string op=j.value("op",std::string("eval"));
        dp::Json output;
        if(op=="config") output=dp::config_json(config);
        else if(op=="eval") output=dp::result_json(dp::evaluate(config,dp::request_from_json(j.at("request")),tracing));
        else if(op=="step") {
          std::optional<dp::Request> r;
          const bool reset=j.value("reset",false),av=j.value("a_valid",false),bv=j.value("b_valid",false),cv=j.value("c_valid",false);
          if(!reset && av && bv && cv && j.contains("request")) r=dp::request_from_json(j.at("request"));
          output=dp::tick_json(pipeline.step(r,av,bv,cv,reset));
        } else throw std::invalid_argument("unknown operation");
        std::cout<<output.dump()<<'\n';
      } catch(const std::exception& e) {
        failed=true; std::cout<<dp::Json({{"error",e.what()}}).dump()<<'\n';
      }
    }
    return failed?2:0;
  } catch(const std::exception& e) { std::cerr<<e.what()<<'\n'; return 2; }
}
