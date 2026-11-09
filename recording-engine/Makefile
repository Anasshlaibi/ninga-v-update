CC ?= gcc
CROSS_CC ?= aarch64-linux-gnu-gcc
CFLAGS ?= -O3 -Wall -Wextra -pthread -D_GNU_SOURCE
LDFLAGS ?= -pthread

HOST_TARGETS = vraw_daemon storage/cinemadng_ring_writer
ARM64_TARGETS = vraw_daemon_arm64 storage/cinemadng_ring_writer_arm64

.PHONY: all arm64 clean test

all: $(HOST_TARGETS)

arm64: $(ARM64_TARGETS)

vraw_daemon: vraw_daemon.c
	$(CC) $(CFLAGS) $< -o $@ $(LDFLAGS)

storage/cinemadng_ring_writer: storage/cinemadng_ring_writer.c
	$(CC) $(CFLAGS) $< -o $@ $(LDFLAGS)

vraw_daemon_arm64: vraw_daemon.c
	$(CROSS_CC) $(CFLAGS) $< -o $@ $(LDFLAGS)

storage/cinemadng_ring_writer_arm64: storage/cinemadng_ring_writer.c
	$(CROSS_CC) $(CFLAGS) $< -o $@ $(LDFLAGS)

test: vraw_daemon
	./vraw_daemon --standalone 24 /tmp/vraw_daemon_test

clean:
	rm -f $(HOST_TARGETS) $(ARM64_TARGETS)

