/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */

#include <folly/json.h>
#include <memory>
#include <string>
#include <string_view>
#include "beanmachine/minibmg/graph.h"

namespace {

using namespace beanmachine::minibmg;
using dynamic = folly::dynamic;

inline constexpr auto hash_djb2a(const std::string_view sv) {
  unsigned long hash{5381};
  for (unsigned char c : sv) {
    hash = ((hash << 5) + hash) ^ c;
  }
  return hash;
}

inline constexpr auto // NOLINT: this is used to effectively switch on a string
                      // below. If we replace that implementation by one that
                      // indexes a table of functions on a string, this would
                      // not be necessary.
operator"" _sh(const char* str, size_t len) {
  return hash_djb2a(std::string_view{str, len});
}

class JsonNodeWriterVisitor : public NodeVisitor {
 public:
  explicit JsonNodeWriterVisitor(dynamic& dyn_node) : dyn_node{dyn_node} {}
  dynamic& dyn_node;
  void visit(const ScalarConstantNode* node) override {
    dyn_node["operator"] = "CONSTANT";
    dyn_node["value"] = node->constant_value;
  }
  void visit(const ScalarVariableNode* node) override {
    dyn_node["operator"] = "VARIABLE";
    dyn_node["name"] = node->name;
    dyn_node["identifier"] = node->identifier;
  }
  void visit(const ScalarSampleNode*) override {
    dyn_node["operator"] = "SAMPLE";
  }
  void visit(const ScalarAddNode*) override {
    dyn_node["operator"] = "ADD";
  }
  void visit(const ScalarSubtractNode*) override {
    dyn_node["operator"] = "SUBTRACT";
  }
  void visit(const ScalarNegateNode*) override {
    dyn_node["operator"] = "NEGATE";
  }
  void visit(const ScalarMultiplyNode*) override {
    dyn_node["operator"] = "MULTIPLY";
  }
  void visit(const ScalarDivideNode*) override {
    dyn_node["operator"] = "DIVIDE";
  }
  void visit(const ScalarPowNode*) override {
    dyn_node["operator"] = "POW";
  }
  void visit(const ScalarExpNode*) override {
    dyn_node["operator"] = "EXP";
  }
  void visit(const ScalarLogNode*) override {
    dyn_node["operator"] = "LOG";
  }
  void visit(const ScalarAtanNode*) override {
    dyn_node["operator"] = "ATAN";
  }
  void visit(const ScalarLgammaNode*) override {
    dyn_node["operator"] = "LGAMMA";
  }
  void visit(const ScalarPolygammaNode*) override {
    dyn_node["operator"] = "POLYGAMMA";
  }
  void visit(const ScalarLog1pNode*) override {
    dyn_node["operator"] = "LOG1P";
  }
  void visit(const ScalarIfEqualNode*) override {
    dyn_node["operator"] = "IF_EQUAL";
  }
  void visit(const ScalarIfLessNode*) override {
    dyn_node["operator"] = "IF_LESS";
  }
  void visit(const DistributionNormalNode*) override {
    dyn_node["operator"] = "DISTRIBUTION_NORMAL";
  }
  void visit(const DistributionHalfNormalNode*) override {
    dyn_node["operator"] = "DISTRIBUTION_HALF_NORMAL";
  }
  void visit(const DistributionBetaNode*) override {
    dyn_node["operator"] = "DISTRIBUTION_BETA";
  }
  void visit(const DistributionBernoulliNode*) override {
    dyn_node["operator"] = "DISTRIBUTION_BERNOULLI";
  }
  void visit(const DistributionExponentialNode*) override {
    dyn_node["operator"] = "DISTRIBUTION_EXPONENTIAL";
  }
};

} // namespace

namespace beanmachine::minibmg {

JsonError2::JsonError2(const std::string& message) : message(message) {}

folly::dynamic graph_to_json(const Graph& g) {
  std::unordered_map<Nodep, unsigned long> node_to_identifier;
  dynamic result = dynamic::object;
  result["comment"] = "created by graph_to_json";
  dynamic a = dynamic::array;

  unsigned long next_identifier = 0;
  for (auto& node : g) {
    // assign node identifiers sequentially.  They are called "sequence" in the
    // generated json.
    auto identifier = next_identifier++;
    node_to_identifier[node] = identifier;
    dynamic dyn_node = dynamic::object;
    dyn_node["sequence"] = identifier;
    JsonNodeWriterVisitor v{dyn_node};
    node->accept(v);
    auto in = in_nodes(node);
    if (in.size() > 0) {
      dynamic in_nodes = dynamic::array;
      for (auto& n : in) {
        in_nodes.push_back(node_to_identifier[n]);
      }
      dyn_node["in_nodes"] = in_nodes;
    }

    a.push_back(dyn_node);
  }
  result["nodes"] = a;

  dynamic observations = dynamic::array;
  for (auto& q : g.observations) {
    dynamic d = dynamic::object;
    auto id = node_to_identifier[q.first];
    d["node"] = id;
    d["value"] = q.second;
    observations.push_back(d);
  }
  result["observations"] = observations;

  dynamic queries = dynamic::array;
  for (auto& q : g.queries) {
    queries.push_back(node_to_identifier[q]);
  }
  result["queries"] = queries;

  return result;
}

} // namespace beanmachine::minibmg

namespace {

Nodep json_to_node( // NOLINT: large cyclomatic complexity doe not imply code
                    // that is difficult to maintain.  In this case we might be
                    // able to replace the code with a table of functions
                    // indexed by string, but I'm not sure that would be better.
    folly::dynamic json_node,
    std::unordered_map<int, Nodep>& identifier_to_node,
    int& identifier) {
  auto identifierv = json_node["sequence"];
  if (!identifierv.isInt()) {
    throw JsonError2("missing sequence number.");
  }
  identifier = identifierv.asInt();

  auto opv = json_node["operator"];
  if (!opv.isString()) {
    throw JsonError2("missing operator.");
  }

  std::vector<Nodep> in_nodes{};
  switch (hash_djb2a(opv.asString())) {
    case "CONSTANT"_sh:
    case "VARIABLE"_sh:
      // in_nodes ignored
      break;
    default:
      auto in_nodesv = json_node["in_nodes"];
      if (!in_nodesv.isArray()) {
        throw JsonError2("missing in_nodes.");
      }
      for (auto& in_nodev : in_nodesv) {
        if (!in_nodev.isInt()) {
          throw JsonError2("missing in_node for operator.");
        }
        auto in_node_i = in_nodev.asInt();
        if (!identifier_to_node.contains(in_node_i)) {
          throw JsonError2("bad in_node for operator.");
        }
        auto in_node = identifier_to_node[in_node_i];
        in_nodes.push_back(in_node);
      }
      break;
  }

  switch (hash_djb2a(opv.asString())) {
    case "CONSTANT"_sh: {
      auto valuev = json_node["value"];
      double value;
      if (valuev.isInt()) {
        value = valuev.asInt();
      } else if (valuev.isDouble()) {
        value = valuev.asDouble();
      } else {
        throw JsonError2("bad value for constant.");
      }
      return std::make_shared<const ScalarConstantNode>(value);
    }
    case "VARIABLE"_sh: {
      auto namev = json_node["name"];
      std::string name = "";
      if (namev.isString()) {
        name = namev.asString();
      } else {
        throw JsonError2("bad name for variable.");
      }
      auto variable_indexv = json_node["variable_index"];
      if (!variable_indexv.isInt()) {
        throw JsonError2("bad variable_index for variable.");
      }
      auto variable_index = (unsigned)variable_indexv.asInt();
      return std::make_shared<const ScalarVariableNode>(name, variable_index);
    }
    case "ADD"_sh: {
      if (in_nodes.size() != 2) {
        throw JsonError2("bad in_node for operator.");
      }
      return std::make_shared<ScalarAddNode>(
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[0]),
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[1]));
    }
    case "SUBTRACT"_sh: {
      if (in_nodes.size() != 2) {
        throw JsonError2("bad in_node for operator.");
      }
      return std::make_shared<ScalarSubtractNode>(
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[0]),
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[1]));
    }
    case "NEGATE"_sh: {
      if (in_nodes.size() != 1) {
        throw JsonError2("bad in_node for operator.");
      }
      return std::make_shared<ScalarNegateNode>(
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[0]));
    }
    case "MULTIPLY"_sh: {
      if (in_nodes.size() != 2) {
        throw JsonError2("bad in_node for operator.");
      }
      return std::make_shared<ScalarMultiplyNode>(
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[0]),
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[1]));
    }
    case "DIVIDE"_sh: {
      if (in_nodes.size() != 2) {
        throw JsonError2("bad in_node for operator.");
      }
      return std::make_shared<ScalarDivideNode>(
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[0]),
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[1]));
    }
    case "POW"_sh: {
      if (in_nodes.size() != 2) {
        throw JsonError2("bad in_node for operator.");
      }
      return std::make_shared<ScalarPowNode>(
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[0]),
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[1]));
    }
    case "EXP"_sh: {
      if (in_nodes.size() != 1) {
        throw JsonError2("bad in_node for operator.");
      }
      return std::make_shared<ScalarExpNode>(
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[0]));
    }
    case "LOG"_sh: {
      if (in_nodes.size() != 1) {
        throw JsonError2("bad in_node for operator.");
      }
      return std::make_shared<ScalarLogNode>(
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[0]));
    }
    case "ATAN"_sh: {
      if (in_nodes.size() != 1) {
        throw JsonError2("bad in_node for operator.");
      }
      return std::make_shared<ScalarAtanNode>(
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[0]));
    }
    case "LGAMMA"_sh: {
      if (in_nodes.size() != 1) {
        throw JsonError2("bad in_node for operator.");
      }
      return std::make_shared<ScalarLgammaNode>(
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[0]));
    }
    case "POLYGAMMA"_sh: {
      if (in_nodes.size() != 2) {
        throw JsonError2("bad in_node for operator.");
      }
      return std::make_shared<ScalarPolygammaNode>(
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[0]),
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[1]));
    }
    case "LOG1P"_sh: {
      if (in_nodes.size() != 1) {
        throw JsonError2("bad in_node for operator.");
      }
      return std::make_shared<ScalarLog1pNode>(
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[0]));
    }
    case "IF_EQUAL"_sh: {
      if (in_nodes.size() != 4) {
        throw JsonError2("bad in_node for operator.");
      }
      return std::make_shared<ScalarIfEqualNode>(
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[0]),
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[1]),
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[2]),
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[3]));
    }
    case "IF_LESS"_sh: {
      if (in_nodes.size() != 4) {
        throw JsonError2("bad in_node for operator.");
      }
      return std::make_shared<ScalarIfLessNode>(
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[0]),
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[1]),
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[2]),
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[3]));
    }
    case "DISTRIBUTION_NORMAL"_sh: {
      if (in_nodes.size() != 2) {
        throw JsonError2("bad in_node for operator.");
      }
      return std::make_shared<DistributionNormalNode>(
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[0]),
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[1]));
    }
    case "DISTRIBUTION_HALF_NORMAL"_sh: {
      if (in_nodes.size() != 1) {
        throw JsonError2("bad in_node for operator.");
      }
      return std::make_shared<DistributionHalfNormalNode>(
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[0]));
      break;
    }
    case "DISTRIBUTION_BETA"_sh: {
      if (in_nodes.size() != 2) {
        throw JsonError2("bad in_node for operator.");
      }
      return std::make_shared<DistributionBetaNode>(
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[0]),
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[1]));
    }
    case "DISTRIBUTION_BERNOULLI"_sh: {
      if (in_nodes.size() != 1) {
        throw JsonError2("bad in_node for operator.");
      }
      return std::make_shared<DistributionBernoulliNode>(
          std::dynamic_pointer_cast<const ScalarNode>(in_nodes[0]));
    }
    case "SAMPLE"_sh: {
      if (in_nodes.size() != 1) {
        throw JsonError2("bad in_node for operator.");
      }
      return std::make_shared<ScalarSampleNode>(
          std::dynamic_pointer_cast<const DistributionNode>(in_nodes[0]));
    }
    default:
      throw JsonError2("operator unknown: " + opv.asString());
  }
}

} // namespace

namespace beanmachine::minibmg {

Graph json_to_graph2(folly::dynamic d) {
  // Nodes are identified by a "sequence" number appearing in json.
  // They are arbitrary numbers.  The only requirement is that they
  // are distinct.  They are used to identify nodes in the json.
  // This map is used to identify the specific node when it is
  // referenced in the json.
  std::unordered_map<int, Nodep> identifier_to_node;

  auto json_nodes = d["nodes"];
  if (!json_nodes.isArray()) {
    throw JsonError2("missing \"nodes\" property");
  }

  for (auto json_node : json_nodes) {
    int identifier;
    auto node = json_to_node(json_node, identifier_to_node, identifier);
    if (identifier_to_node.contains(identifier)) {
      throw JsonError2(fmt::format("duplicate node ID {}.", identifier));
    }
    identifier_to_node[identifier] = node;
  }

  std::vector<Nodep> queries;
  auto query_nodes = d["queries"];
  if (query_nodes.isArray()) {
    for (auto& query : query_nodes) {
      if (!query.isInt()) {
        throw JsonError2("bad query value.");
      }
      auto query_i = query.asInt();
      if (!identifier_to_node.contains(query_i)) {
        throw JsonError2(fmt::format("bad in_node {} for query.", query_i));
      }
      auto query_node = identifier_to_node[query_i];
      queries.push_back(query_node);
    }
  }

  std::vector<std::pair<Nodep, double>> observations;
  auto observation_nodes = d["observations"];
  if (observation_nodes.isArray()) {
    for (auto& obs : observation_nodes) {
      auto node = obs["node"];
      if (!node.isInt()) {
        throw JsonError2("bad observation node.");
      }
      auto node_i = node.asInt();
      if (!identifier_to_node.contains(node_i)) {
        throw JsonError2(
            fmt::format("bad in_node {} for observation.", node_i));
      }
      auto& obs_node = identifier_to_node[node_i];
      auto& value = obs["value"];
      if (!node.isDouble() && !node.isInt()) {
        throw JsonError2("bad value for observation.");
      }
      auto value_d = value.asDouble();
      observations.push_back(std::pair{obs_node, value_d});
    }
  }

  return Graph::create(queries, observations);
}

} // namespace beanmachine::minibmg
