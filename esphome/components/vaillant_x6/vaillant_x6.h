#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/uart/uart.h"
#include "esphome/core/component.h"

namespace esphome {
namespace vaillant_x6 {

enum class ValueType : uint8_t {
  TEMPERATURE,
  BOOL,
  MINUTES,
};

struct Request {
  uint8_t address;
  ValueType type;
  sensor::Sensor *sensor;
  binary_sensor::BinarySensor *binary_sensor;
};

/// Polls the Vaillant X6 diagnostic interface. Read-only: only request
/// packets for reading values are ever sent. Communication is non-blocking;
/// one request is in flight at a time and handled in loop().
class VaillantX6 : public PollingComponent, public uart::UARTDevice {
 public:
  void setup() override;
  void loop() override;
  void update() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

  void add_sensor(uint8_t address, ValueType type, sensor::Sensor *sensor);
  void add_binary_sensor(uint8_t address, binary_sensor::BinarySensor *sensor);
  void set_connected_sensor(binary_sensor::BinarySensor *sensor) { this->connected_sensor_ = sensor; }
  void set_error_sensor(sensor::Sensor *sensor) { this->error_sensor_ = sensor; }
  void set_response_timeout(uint32_t ms) { this->response_timeout_ = ms; }
  void set_request_gap(uint32_t ms) { this->request_gap_ = ms; }

  /// Checksum used by the X6 protocol for requests and responses.
  static uint8_t checksum(const uint8_t *data, size_t length);

 protected:
  enum class State : uint8_t { IDLE, WAIT_GAP, WAIT_RESPONSE };

  static constexpr size_t REQUEST_LENGTH = 7;
  static constexpr size_t MAX_RESPONSE_LENGTH = 16;

  void send_request_();
  void handle_response_(size_t length);
  void finish_request_(bool ok);
  void drain_rx_();

  std::vector<Request> requests_;
  State state_{State::IDLE};
  size_t index_{0};
  uint32_t timestamp_{0};
  uint8_t buffer_[MAX_RESPONSE_LENGTH]{};
  size_t received_{0};
  bool cycle_ok_{false};
  uint32_t errors_{0};
  uint32_t response_timeout_{500};
  uint32_t request_gap_{100};

  binary_sensor::BinarySensor *connected_sensor_{nullptr};
  sensor::Sensor *error_sensor_{nullptr};
};

}  // namespace vaillant_x6
}  // namespace esphome
