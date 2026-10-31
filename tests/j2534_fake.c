/*
 * A fake J2534 library for the tests of the 32 bit helper (gkbus/device/j2534/helper).
 * Builds as a shared object, and as a 32 bit DLL with mingw-w64 (-Wl,--kill-at).
 *
 * - device id 1, opening "busy" fails with ERR_DEVICE_IN_USE
 * - PassThruConnect returns the protocol id + 100 as channel id
 * - written messages come back from PassThruReadMsgs, with the timestamp counting up
 * - a filter's id is type * 10, + 1 if it has a flow control message
 * - pin 2 can't take a programming voltage (0x77 like the OpenPort)
 * - ioctls: GET/SET_CONFIG keep the values (default: parameter * 2), READ_VBATT 12345,
 *   READ_PROG_VOLTAGE 8000, FAST_INIT answers the request reversed, FIVE_BAUD_INIT answers
 *   0x08 and the address inverted, FORCE_STATUS (0x10000, ULONG in) makes the next call
 *   return that status after doing its work
 * - opening and closing is logged to the file in J2534_FAKE_LOG, if it's set
 */

#define _POSIX_C_SOURCE 199309L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <windows.h>
#define EXPORT __declspec(dllexport) long WINAPI
#define sleep_ms(ms) Sleep(ms)
#else
#include <time.h>
#define EXPORT __attribute__((visibility("default"))) long
static void sleep_ms (unsigned long ms) {
	struct timespec t = { ms / 1000, (ms % 1000) * 1000000L };
	nanosleep(&t, NULL);
}
#endif

#define MSG_DATA_MAX 4128
#define QUEUE_SIZE 64

typedef struct {
	unsigned long ProtocolID, RxStatus, TxFlags, Timestamp, DataSize, ExtraDataIndex;
	unsigned char Data[MSG_DATA_MAX];
} PASSTHRU_MSG;

typedef struct { unsigned long Parameter, Value; } SCONFIG;
typedef struct { unsigned long NumOfParams; SCONFIG *ConfigPtr; } SCONFIG_LIST;
typedef struct { unsigned long NumOfBytes; unsigned char *BytePtr; } SBYTE_ARRAY;

static PASSTHRU_MSG queue[QUEUE_SIZE];
static int queued;
static unsigned long timestamp;
static unsigned long config[256];
static int config_set[256];
static long forced;
static char last_error[80];

static void note (const char *what) {
	const char *path = getenv("J2534_FAKE_LOG");
	FILE *log = path ? fopen(path, "a") : NULL;
	if (log) {
		fprintf(log, "%s\n", what);
		fclose(log);
	}
}

static long done (long status) {
	if (forced) {
		status = forced;
		forced = 0;
	}
	if (status)
		snprintf(last_error, sizeof last_error, "fake failed with 0x%02lX", (unsigned long) status);
	return status;
}

static long fail (long status, const char *text) {
	snprintf(last_error, sizeof last_error, "%s", text);
	return status;
}

EXPORT PassThruOpen (void *name, unsigned long *device_id) {
	if (name && strcmp(name, "busy") == 0)
		return fail(0x0E, "the fake is busy");
	*device_id = 1;
	note("open");
	return done(0);
}

EXPORT PassThruClose (unsigned long device_id) {
	if (device_id != 1)
		return fail(0x1A, "no such device");
	note("close");
	return done(0);
}

EXPORT PassThruConnect (unsigned long device_id, unsigned long protocol, unsigned long flags,
		unsigned long baudrate, unsigned long *channel_id) {
	(void) flags;
	(void) baudrate;
	if (device_id != 1)
		return fail(0x1A, "no such device");
	*channel_id = protocol + 100;
	return done(0);
}

EXPORT PassThruDisconnect (unsigned long channel_id) {
	(void) channel_id;
	return done(0);
}

EXPORT PassThruReadMsgs (unsigned long channel_id, PASSTHRU_MSG *msgs, unsigned long *count,
		unsigned long timeout) {
	unsigned long n = 0;
	(void) channel_id;
	if (!queued && timeout) {
		sleep_ms(timeout);
		*count = 0;
		return done(0x09);
	}
	while (n < *count && queued) {
		msgs[n++] = queue[0];
		memmove(queue, queue + 1, --queued * sizeof *queue);
	}
	*count = n;
	return done(n ? 0 : 0x10);
}

EXPORT PassThruWriteMsgs (unsigned long channel_id, PASSTHRU_MSG *msgs, unsigned long *count,
		unsigned long timeout) {
	unsigned long i;
	(void) channel_id;
	(void) timeout;
	for (i = 0; i < *count && queued < QUEUE_SIZE; i++) {
		queue[queued] = msgs[i];
		queue[queued++].Timestamp = ++timestamp;
	}
	*count = i;
	return done(0);
}

EXPORT PassThruStartPeriodicMsg (unsigned long channel_id, PASSTHRU_MSG *msg,
		unsigned long *msg_id, unsigned long interval) {
	(void) channel_id;
	(void) msg;
	(void) msg_id;
	(void) interval;
	return fail(0x01, "no periodic messages");
}

EXPORT PassThruStopPeriodicMsg (unsigned long channel_id, unsigned long msg_id) {
	(void) channel_id;
	(void) msg_id;
	return fail(0x01, "no periodic messages");
}

EXPORT PassThruStartMsgFilter (unsigned long channel_id, unsigned long type, PASSTHRU_MSG *mask,
		PASSTHRU_MSG *pattern, PASSTHRU_MSG *flow_control, unsigned long *filter_id) {
	(void) channel_id;
	if (mask->DataSize != pattern->DataSize)
		return fail(0x0A, "mask and pattern differ in size");
	*filter_id = type * 10 + (flow_control ? 1 : 0);
	return done(0);
}

EXPORT PassThruStopMsgFilter (unsigned long channel_id, unsigned long filter_id) {
	(void) channel_id;
	(void) filter_id;
	return done(0);
}

EXPORT PassThruSetProgrammingVoltage (unsigned long device_id, unsigned long pin,
		unsigned long voltage) {
	(void) device_id;
	(void) voltage;
	if (pin == 2)
		return fail(0x77, "voltage too high for pin 2");
	return done(0);
}

EXPORT PassThruReadVersion (unsigned long device_id, char *firmware, char *dll, char *api) {
	(void) device_id;
	strcpy(firmware, "1.17.4877");
	strcpy(dll, "fake 1.0");
	strcpy(api, "04.04");
	return done(0);
}

EXPORT PassThruGetLastError (char *description) {
	strcpy(description, last_error);
	return 0;
}

EXPORT PassThruIoctl (unsigned long channel_id, unsigned long ioctl_id, void *in, void *out) {
	unsigned long i;
	(void) channel_id;
	switch (ioctl_id) {
	case 0x01: { /* GET_CONFIG */
		SCONFIG_LIST *list = in;
		for (i = 0; i < list->NumOfParams; i++) {
			unsigned long p = list->ConfigPtr[i].Parameter & 0xFF;
			list->ConfigPtr[i].Value = config_set[p] ? config[p] : p * 2;
		}
		return done(0);
	}
	case 0x02: { /* SET_CONFIG */
		SCONFIG_LIST *list = in;
		for (i = 0; i < list->NumOfParams; i++) {
			unsigned long p = list->ConfigPtr[i].Parameter & 0xFF;
			config[p] = list->ConfigPtr[i].Value;
			config_set[p] = 1;
		}
		return done(0);
	}
	case 0x03: /* READ_VBATT */
		*(unsigned long *) out = 12345;
		return done(0);
	case 0x0E: /* READ_PROG_VOLTAGE */
		*(unsigned long *) out = 8000;
		return done(0);
	case 0x04: { /* FIVE_BAUD_INIT */
		SBYTE_ARRAY *address = in, *key_bytes = out;
		if (key_bytes->NumOfBytes < 2)
			return fail(0x11, "key byte buffer too small");
		key_bytes->BytePtr[0] = 0x08;
		key_bytes->BytePtr[1] = ~address->BytePtr[0];
		key_bytes->NumOfBytes = 2;
		return done(0);
	}
	case 0x05: { /* FAST_INIT */
		PASSTHRU_MSG *request = in, *response = out;
		*response = *request;
		for (i = 0; i < request->DataSize; i++)
			response->Data[i] = request->Data[request->DataSize - 1 - i];
		response->RxStatus = 0;
		return done(0);
	}
	case 0x07: /* CLEAR_TX_BUFFER */
		return done(0);
	case 0x08: /* CLEAR_RX_BUFFER */
		queued = 0;
		return done(0);
	case 0x10000: /* FORCE_STATUS */
		forced = (long) *(unsigned long *) in;
		return 0;
	}
	return fail(0x0F, "unknown ioctl");
}
