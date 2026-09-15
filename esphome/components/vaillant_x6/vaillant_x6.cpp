#include "vaillant_x6.h"

#include <cinttypes>

#include "esphome/core/hal.h"
#include "esphome/core/log.h"

namespace esphome {
namespace vaillant_x6 {

static const char *const TAG = "vaillant_x6";

// Protocol (reverse engineered, see README):
//   request:  07 00 00 00 <address> <request byte> <checksum>
//             request byte: 0x05 on older boilers (e.g. VKO/VKK), 0x00 on newer ones
//   response: <length> <status> <data...> <checksum>
// <length> counts the whole packet. Temperatures are big-endian int16 / 16.
static const uint8_t REQUEST_PREFIX[] = {0x07, 0x00, 0x00, 0x00};

static const float MIN_PLAUSIBLE_TEMPERATURE = -20.0f;
static const float MAX_PLAUSIBLE_TEMPERATURE = 120.0f;

uint8_t VaillantX6::checksum(const uint8_t *data, size_t length) {
  uint8_t sum = 0;
  for (size_t i = 0; i < length; i++) {
    if (sum & 0x80) {
      sum = static_cast<uint8_t>((sum << 1) | 1);
      sum ^= 0x18;
    } else {
      sum = static_cast<uint8_t>(sum << 1);
    }
    sum ^= data[i];
  }
  return sum;
}

void VaillantX6::add_sensor(uint8_t address, ValueType type, sensor::Sensor *sensor) {
  this->requests_.push_back(Request{address, type, sensor, nullptr});
}

void VaillantX6::add_binary_sensor(uint8_t address, binary_sensor::BinarySensor *sensor) {
  this->requests_.push_back(Request{address, ValueType::BOOL, nullptr, sensor});
}

void VaillantX6::setup() { this->drain_rx_(); }

void VaillantX6::dump_config() {
  ESP_LOGCONFIG(TAG, "Vaillant X6 (read-only):");
  ESP_LOGCONFIG(TAG, "  Requests per cycle: %u", static_cast<unsigned>(this->requests_.size()));
  ESP_LOGCONFIG(TAG, "  Response timeout: %" PRIu32 " ms", this->response_timeout_);
  ESP_LOGCONFIG(TAG, "  Request gap: %" PRIu32 " ms", this->request_gap_);
  ESP_LOGCONFIG(TAG, "  Request byte: 0x%02X%s", this->request_byte_,
                this->auto_request_byte_ ? " (auto)" : "");
  LOG_UPDATE_INTERVAL(this);
}

void VaillantX6::update() {
  if (this->requests_.empty()) {
    return;
  }
  if (this->state_ != State::IDLE) {
    ESP_LOGW(TAG, "Previous polling cycle still running, skipping update");
    return;
  }
  this->index_ = 0;
  this->cycle_ok_ = false;
  this->send_request_();
}

void VaillantX6::loop() {
  switch (this->state_) {
    case State::IDLE:
      return;

    case State::WAIT_GAP:
      if (millis() - this->timestamp_ >= this->request_gap_) {
        this->send_request_();
      }
      return;

    case State::WAIT_RESPONSE: {
      uint8_t byte;
      while (this->received_ < MAX_RESPONSE_LENGTH && this->available() && this->read_byte(&byte)) {
        this->buffer_[this->received_++] = byte;
      }
      if (this->received_ > 0) {
        size_t expected = this->buffer_[0];
        if (expected < 4 || expected > MAX_RESPONSE_LENGTH) {
          ESP_LOGW(TAG, "Address 0x%02X: invalid response length %u", this->requests_[this->index_].address,
                   static_cast<unsigned>(expected));
          this->finish_request_(false);
          return;
        }
        if (this->received_ >= expected) {
          this->handle_response_(expected);
          return;
        }
      }
      if (millis() - this->timestamp_ > this->response_timeout_) {
        ESP_LOGD(TAG, "Address 0x%02X: no complete response (%u bytes)", this->requests_[this->index_].address,
                 static_cast<unsigned>(this->received_));
        this->finish_request_(false);
      }
      return;
    }
  }
}

void VaillantX6::send_request_() {
  const Request &request = this->requests_[this->index_];
  uint8_t packet[REQUEST_LENGTH];
  for (size_t i = 0; i < sizeof(REQUEST_PREFIX); i++) {
    packet[i] = REQUEST_PREFIX[i];
  }
  packet[4] = request.address;
  packet[5] = this->request_byte_;
  packet[6] = checksum(packet, REQUEST_LENGTH - 1);

  this->drain_rx_();
  this->received_ = 0;
  this->write_array(packet, REQUEST_LENGTH);
  ESP_LOGV(TAG, "TX %02X %02X %02X %02X %02X %02X %02X", packet[0], packet[1], packet[2], packet[3], packet[4],
           packet[5], packet[6]);
  this->timestamp_ = millis();
  this->state_ = State::WAIT_RESPONSE;
}

void VaillantX6::handle_response_(size_t length) {
  const Request &request = this->requests_[this->index_];
  const uint8_t *data = this->buffer_;

  if (checksum(data, length - 1) != data[length - 1]) {
    ESP_LOGW(TAG, "Address 0x%02X: checksum mismatch", request.address);
    this->finish_request_(false);
    return;
  }

  switch (request.type) {
    case ValueType::TEMPERATURE: {
      if (length < 5) {
        ESP_LOGW(TAG, "Address 0x%02X: response too short for a temperature", request.address);
        this->finish_request_(false);
        return;
      }
      int16_t raw = static_cast<int16_t>((data[2] << 8) | data[3]);
      float value = raw / 16.0f;
      if (value < MIN_PLAUSIBLE_TEMPERATURE || value > MAX_PLAUSIBLE_TEMPERATURE) {
        ESP_LOGW(TAG, "Address 0x%02X: implausible temperature %.1f", request.address, value);
        this->finish_request_(false);
        return;
      }
      request.sensor->publish_state(value);
      break;
    }
    case ValueType::MINUTES:
      request.sensor->publish_state(data[2]);
      break;
    case ValueType::BOOL:
      if (data[2] == 0x00 || data[2] == 0xF0) {
        request.binary_sensor->publish_state(false);
      } else if (data[2] == 0x01 || data[2] == 0x0F) {
        request.binary_sensor->publish_state(true);
      } else {
        ESP_LOGW(TAG, "Address 0x%02X: unknown boolean value 0x%02X", request.address, data[2]);
        this->finish_request_(false);
        return;
      }
      break;
  }
  this->finish_request_(true);
}

void VaillantX6::finish_request_(bool ok) {
  if (ok) {
    this->cycle_ok_ = true;
  } else {
    this->errors_++;
  }
  this->received_ = 0;
  this->index_++;

  if (this->index_ < this->requests_.size()) {
    this->timestamp_ = millis();
    this->state_ = State::WAIT_GAP;
    return;
  }

  this->state_ = State::IDLE;
  this->update_request_byte_();
  if (this->connected_sensor_ != nullptr) {
    this->connected_sensor_->publish_state(this->cycle_ok_);
  }
  if (this->error_sensor_ != nullptr) {
    this->error_sensor_->publish_state(this->errors_);
  }
}

void VaillantX6::update_request_byte_() {
  if (this->cycle_ok_) {
    this->failed_cycles_ = 0;
    if (this->auto_request_byte_ && !this->request_byte_detected_) {
      this->request_byte_detected_ = true;
      ESP_LOGI(TAG, "Boiler answers with request byte 0x%02X", this->request_byte_);
    }
    return;
  }
  if (this->failed_cycles_ < 255) {
    this->failed_cycles_++;
  }
  ESP_LOGW(TAG, "No valid response in this cycle (request byte 0x%02X)", this->request_byte_);
  if (!this->auto_request_byte_) {
    return;
  }
  // Before detection try the other variant after every silent cycle; after detection
  // only when the boiler has been silent for a while (e.g. it was switched off).
  if (!this->request_byte_detected_ || this->failed_cycles_ >= 10) {
    this->request_byte_detected_ = false;
    this->failed_cycles_ = 0;
    this->request_byte_ = this->request_byte_ == 0x05 ? 0x00 : 0x05;
    ESP_LOGI(TAG, "Trying request byte 0x%02X", this->request_byte_);
  }
}

void VaillantX6::drain_rx_() {
  uint8_t byte;
  while (this->available() && this->read_byte(&byte)) {
  }
}

}  // namespace vaillant_x6
}  // namespace esphome
